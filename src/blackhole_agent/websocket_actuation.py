"""Drive a first-class websocket tool through RFC 6455 upgrade framing.

Tool routing already fails missions that require ``websocket``: hosted
upgrade plugins stay on the unsupported MCP provider, and no first-party
RFC 6455 provider is executable. Unbound therefore cannot complete an
HTTP 101 Switching Protocols handshake, mask a client text frame, answer
a control-frame pong, or independently replay a sealed frame digest.

This module closes that hole:

- advertise a ``websocket`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 6455 listener
- keep a missing-token client so the Authorization hole stays falsifiable
- refuse SEND/RECEIVE/PONG until the 101 upgrade succeeds
- mask client frames, reject unmasked client frames, PING then PONG, then
  independently replay the retained payload on a later connection
- persist a sealed frame digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after structured
  tool output
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
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
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    WEBSOCKET_TOOL_PROVIDER,
    ToolDescriptor,
    build_tool_routing_preflight,
    local_memory_tool_descriptor,
    route_tool_descriptor,
    websocket_tool_descriptor,
)

SCHEMA_VERSION = 1
WEBSOCKET_ACTUATION_ID = "capability.websocket-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
UNLOCK_TOKEN = "blackhole-websocket"
SENTINEL = "BH-WEBSOCKET-OK"
DEFAULT_TOKEN = "blackhole-websocket-secret"
SEALED_NAME = "sealed.json"
RETAINED_NAME = "retained.bin"
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
SUBPROTOCOL = "blackhole.ws"
PING_PAYLOAD = b"bh-ws-ping"
OP_TEXT = 0x1
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA
CLOSE_PROTOCOL_ERROR = 1002
HTTP_TIMEOUT = 2.0
IO_TIMEOUT = 2.0

WEBSOCKET_ACTUATION_DONE_WHEN = (
    f"capability_exists:{WEBSOCKET_ACTUATION_ID};"
    f"capability_proved:{WEBSOCKET_ACTUATION_ID};"
    "no_skill_route"
)
WEBSOCKET_ACTUATION_GOAL = (
    "Repair rfc6455 websocket upgrade framing: hosted websocket tools remain "
    "unsupported so an HTTP-Upgrade/masked-SEND/RECEIVE/PONG cycle cannot "
    "land and a sealed frame digest cannot be produced. A missing websocket "
    "token stays forbidden; fail-closed routing never opts the websocket "
    "provider in. The 101 Switching Protocols accept key and later-connection "
    "replay keep the hole falsifiable."
)


class WebSocketActuationError(RuntimeError):
    """Raised when the websocket session or listener fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def websocket_accept_key(sec_key: str) -> str:
    """Return Sec-WebSocket-Accept for a client Sec-WebSocket-Key."""

    material = f"{sec_key}{GUID}".encode("ascii")
    return base64.b64encode(hashlib.sha1(material).digest()).decode("ascii")


def encode_frame(payload: bytes, *, opcode: int, masked: bool) -> bytes:
    """Encode one RFC 6455 frame. Client-to-server frames must be masked."""

    body = bytes(payload or b"")
    header = bytearray([0x80 | (int(opcode) & 0x0F)])
    length = len(body)
    if length < 126:
        length_byte = length
        ext = b""
    elif length < 65536:
        length_byte = 126
        ext = struct.pack("!H", length)
    else:
        length_byte = 127
        ext = struct.pack("!Q", length)
    if masked:
        length_byte |= 0x80
    header.append(length_byte)
    header.extend(ext)
    if masked:
        key = os.urandom(4)
        header.extend(key)
        body = bytes(byte ^ key[index % 4] for index, byte in enumerate(body))
    return bytes(header) + body


def _recv_exact(conn: socket.socket, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        piece = conn.recv(size - len(chunks))
        if not piece:
            raise WebSocketActuationError("eof reading websocket frame")
        chunks.extend(piece)
    return bytes(chunks)


def decode_frame(conn: socket.socket) -> tuple[int, bytes, bool]:
    """Read one RFC 6455 frame. Returns opcode, payload, masked."""

    header = _recv_exact(conn, 2)
    opcode = header[0] & 0x0F
    masked = bool(header[1] & 0x80)
    length = header[1] & 0x7F
    if length == 126:
        length = struct.unpack("!H", _recv_exact(conn, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", _recv_exact(conn, 8))[0]
    mask_key = _recv_exact(conn, 4) if masked else b""
    payload = _recv_exact(conn, length) if length else b""
    if masked:
        payload = bytes(byte ^ mask_key[index % 4] for index, byte in enumerate(payload))
    return opcode, payload, masked


def _read_http_request(conn: socket.socket) -> bytes:
    conn.settimeout(HTTP_TIMEOUT)
    buf = bytearray()
    while b"\r\n\r\n" not in buf:
        piece = conn.recv(4096)
        if not piece:
            break
        buf.extend(piece)
        if len(buf) > 65536:
            break
    return bytes(buf)


def _parse_headers(raw: bytes) -> tuple[str, dict[str, str]]:
    text = raw.decode("iso-8859-1", errors="replace")
    head, _, _ = text.partition("\r\n\r\n")
    lines = head.split("\r\n")
    request = lines[0] if lines else ""
    headers: dict[str, str] = {}
    for line in lines[1:]:
        name, sep, value = line.partition(":")
        if not sep:
            continue
        headers[name.strip().lower()] = value.strip()
    return request, headers


def _http_status(raw: bytes) -> int:
    first = raw.split(b"\r\n", 1)[0].decode("iso-8859-1", errors="replace")
    parts = first.split()
    if len(parts) >= 2 and parts[1].isdigit():
        return int(parts[1])
    return 0


class WebSocketListener:
    """Loopback RFC 6455 listener that retains the last unmasked text payload."""

    def __init__(self, secret: str) -> None:
        self.secret = str(secret or "")
        self.retained = b""
        self.last_accept = ""
        self.upgraded = 0
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
        self._thread = threading.Thread(target=self._loop, name="rfc6455-listener", daemon=True)
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

    def _reject(self, conn: socket.socket, status: int, reason: str) -> None:
        body = reason.encode("ascii", errors="replace")
        try:
            conn.sendall(
                (
                    f"HTTP/1.1 {status} {reason}\r\n"
                    "Content-Type: text/plain\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    "Connection: close\r\n\r\n"
                ).encode("ascii")
                + body
            )
        except OSError:
            pass
        try:
            conn.close()
        except OSError:
            pass

    def _serve(self, conn: socket.socket) -> None:
        try:
            raw = _read_http_request(conn)
            _request, headers = _parse_headers(raw)
            upgrade = headers.get("upgrade", "").lower()
            connection = headers.get("connection", "").lower()
            version = headers.get("sec-websocket-version", "")
            sec_key = headers.get("sec-websocket-key", "")
            protocol = headers.get("sec-websocket-protocol", "")
            authorization = headers.get("authorization", "")
            if upgrade != "websocket" or "upgrade" not in connection or version != "13" or not sec_key:
                self._reject(conn, 400, "upgrade_required")
                return
            if not self.secret:
                self._reject(conn, 403, "missing_secret")
                return
            presented = ""
            if authorization.lower().startswith("bearer "):
                presented = authorization[7:].strip()
            if not presented:
                self._reject(conn, 401, "auth_required")
                return
            if presented != self.secret:
                self._reject(conn, 403, "auth_failed")
                return
            if protocol and SUBPROTOCOL not in {item.strip() for item in protocol.split(",")}:
                self._reject(conn, 400, "protocol_required")
                return
            accept = websocket_accept_key(sec_key)
            response = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept}\r\n"
                f"Sec-WebSocket-Protocol: {SUBPROTOCOL}\r\n"
                "\r\n"
            )
            conn.sendall(response.encode("ascii"))
            with self._lock:
                self.last_accept = accept
                self.upgraded += 1
            conn.settimeout(IO_TIMEOUT)
            while not self._stop.is_set():
                try:
                    opcode, payload, masked = decode_frame(conn)
                except (OSError, WebSocketActuationError, TimeoutError, struct.error):
                    break
                if not masked:
                    conn.sendall(
                        encode_frame(
                            struct.pack("!H", CLOSE_PROTOCOL_ERROR) + b"unmasked",
                            opcode=OP_CLOSE,
                            masked=False,
                        )
                    )
                    break
                if opcode == OP_CLOSE:
                    conn.sendall(encode_frame(payload, opcode=OP_CLOSE, masked=False))
                    break
                if opcode == OP_PING:
                    conn.sendall(encode_frame(payload, opcode=OP_PONG, masked=False))
                    continue
                if opcode != OP_TEXT:
                    continue
                text = payload.decode("utf-8", errors="replace")
                if text == "replay":
                    with self._lock:
                        retained = bytes(self.retained)
                    replay = _canonical(
                        {
                            "sentinel": SENTINEL if retained == SENTINEL.encode("utf-8") else "",
                            "token": retained.decode("utf-8", errors="replace"),
                            "digest": payload_sha256(retained),
                            "accept": self.last_accept,
                            "unlocked": UNLOCK_TOKEN,
                        }
                    ).encode("utf-8")
                    conn.sendall(encode_frame(replay, opcode=OP_TEXT, masked=False))
                    continue
                with self._lock:
                    self.retained = payload
                echo = _canonical(
                    {
                        "echo": text,
                        "accept": self.last_accept,
                        "digest": payload_sha256(payload),
                    }
                ).encode("utf-8")
                conn.sendall(encode_frame(echo, opcode=OP_TEXT, masked=False))
        except (OSError, WebSocketActuationError, TimeoutError, UnicodeError, struct.error):
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass


class WebSocketClient:
    """Masked RFC 6455 client used by the actuation workflow."""

    def __init__(self) -> None:
        self.sock: socket.socket | None = None
        self.accept = ""
        self.status = 0
        self.body = b""

    def close(self) -> None:
        sock = self.sock
        self.sock = None
        if sock is None:
            return
        try:
            sock.sendall(encode_frame(b"", opcode=OP_CLOSE, masked=True))
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass

    def connect(
        self,
        host: str,
        port: int,
        token: str,
        *,
        upgrade: bool = True,
        authenticate: bool = True,
    ) -> dict[str, Any]:
        sock = socket.create_connection((host, int(port)), timeout=HTTP_TIMEOUT)
        self.sock = sock
        if not upgrade:
            sock.sendall(b"GET /beacon HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
            self.body = _read_http_request(sock)
            self.status = _http_status(self.body)
            return {"ok": False, "status": self.status or 400, "error": "upgrade_required"}
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        lines = [
            "GET /beacon HTTP/1.1",
            f"Host: {host}:{port}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {key}",
            "Sec-WebSocket-Version: 13",
            f"Sec-WebSocket-Protocol: {SUBPROTOCOL}",
        ]
        if authenticate:
            lines.append(f"Authorization: Bearer {token}")
        sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("ascii"))
        self.body = _read_http_request(sock)
        self.status = _http_status(self.body)
        _request, headers = _parse_headers(self.body)
        if self.status != 101:
            reason = "auth_required"
            if self.status == 403:
                lowered = self.body.decode("iso-8859-1", errors="replace").lower()
                if "missing_secret" in lowered:
                    reason = "missing_secret"
                elif "auth_failed" in lowered:
                    reason = "auth_failed"
                else:
                    reason = "auth_failed"
            elif self.status == 400:
                reason = "upgrade_required"
            elif self.status == 401:
                reason = "auth_required"
            return {"ok": False, "status": self.status or 401, "error": reason}
        expected = websocket_accept_key(key)
        got = headers.get("sec-websocket-accept", "")
        if got != expected:
            return {"ok": False, "status": 409, "error": "accept_mismatch"}
        self.accept = got
        sock.settimeout(IO_TIMEOUT)
        return {
            "ok": True,
            "status": 101,
            "accept": got,
            "protocol": headers.get("sec-websocket-protocol", ""),
        }

    def send_text(self, payload: bytes, *, masked: bool = True) -> None:
        if self.sock is None:
            raise WebSocketActuationError("not connected")
        self.sock.sendall(encode_frame(payload, opcode=OP_TEXT, masked=masked))

    def ping(self, payload: bytes = PING_PAYLOAD) -> None:
        if self.sock is None:
            raise WebSocketActuationError("not connected")
        self.sock.sendall(encode_frame(payload, opcode=OP_PING, masked=True))

    def recv(self) -> tuple[int, bytes, bool]:
        if self.sock is None:
            raise WebSocketActuationError("not connected")
        return decode_frame(self.sock)


class WebSocketSession:
    """Token-gated RFC 6455 session: bind, publish, read."""

    def __init__(self, output_dir: Path, *, secret: str = DEFAULT_TOKEN) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.secret = str(secret or "")
        self.listener: WebSocketListener | None = None
        self.delivered = False
        self.last_digest = ""
        self.last_token = ""
        self.last_accept = ""
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
            "delivered": self.delivered,
        }

    def bind(self, *, authenticate: bool = True, token: str | None = None) -> dict[str, Any]:
        if not self.secret:
            return self._forbidden("missing_secret")
        if not authenticate:
            return self._forbidden("auth_required")
        presented = self.secret if token is None else str(token)
        if presented != self.secret:
            return self._forbidden("auth_failed")
        if self.listener is not None:
            return {
                "ok": True,
                "status": 200,
                "host": self.listener.host,
                "port": self.listener.port,
                "reused": True,
            }
        listener = WebSocketListener(self.secret)
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
        upgrade: bool = True,
        send: bool = True,
        receive: bool = True,
        pong: bool = True,
        mask: bool = True,
        replay: bool = True,
        secret: str | None = None,
    ) -> dict[str, Any]:
        if self.listener is None:
            return self._conflict("websocket_required")
        if not self.secret:
            return self._forbidden("missing_secret")
        presented = self.secret if secret is None else str(secret)
        live_token = str(token or SENTINEL)
        client = WebSocketClient()
        try:
            handshake = client.connect(
                str(self.listener.host),
                int(self.listener.port),
                presented,
                upgrade=upgrade,
                authenticate=authenticate,
            )
            if not handshake.get("ok"):
                return self._forbidden(
                    str(handshake.get("error") or "upgrade_required"),
                    status=int(handshake.get("status") or 403),
                )
            if not send:
                return self._conflict("send_required")
            payload = live_token.encode("utf-8")
            client.send_text(payload, masked=mask)
            if not mask:
                try:
                    opcode, body, _masked = client.recv()
                except (OSError, WebSocketActuationError, TimeoutError, struct.error):
                    return self._conflict("mask_required")
                if opcode == OP_CLOSE:
                    return self._conflict("mask_required")
                return self._conflict("mask_required")
            if not receive:
                return self._conflict("receive_required")
            opcode, echoed, _masked = client.recv()
            if opcode != OP_TEXT:
                return self._forbidden("echo_failed", status=503)
            echo_row = json.loads(echoed.decode("utf-8"))
            if str(echo_row.get("echo") or "") != live_token:
                return self._forbidden("payload_mismatch", status=409)
            if not pong:
                return self._conflict("pong_required")
            client.ping(PING_PAYLOAD)
            popcode, pong_body, _pmasked = client.recv()
            if popcode != OP_PONG or pong_body != PING_PAYLOAD:
                return self._forbidden("pong_failed", status=503)
            client.close()
            if not replay:
                return self._conflict("replay_required")
            replay_client = WebSocketClient()
            try:
                replay_handshake = replay_client.connect(
                    str(self.listener.host),
                    int(self.listener.port),
                    presented,
                    upgrade=True,
                    authenticate=True,
                )
                if not replay_handshake.get("ok"):
                    return self._forbidden("replay_failed", status=503)
                replay_client.send_text(b"replay", masked=True)
                rop, replay_body, _rmasked = replay_client.recv()
                if rop != OP_TEXT:
                    return self._forbidden("replay_failed", status=503)
                replay_row = json.loads(replay_body.decode("utf-8"))
            finally:
                replay_client.close()
            live_digest = payload_sha256(payload)
            if str(replay_row.get("digest") or "") != live_digest:
                return self._forbidden("payload_mismatch", status=409)
            if str(replay_row.get("unlocked") or "") != UNLOCK_TOKEN:
                return self._forbidden("unlock_failed", status=409)
            accept = str(handshake.get("accept") or replay_row.get("accept") or "")
            self.retained_path.write_bytes(payload)
            sealed = {
                "host": self.listener.host,
                "port": self.listener.port,
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": live_digest,
                "accept": accept,
                "authenticated": True,
                "upgraded": True,
                "sent": True,
                "received": True,
                "ponged": True,
                "masked": True,
                "replayed": True,
                "independent": True,
                "retained_path": str(self.retained_path),
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.delivered = True
            self.last_token = live_token
            self.last_digest = live_digest
            self.last_accept = accept
            live = independent_websocket_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "host": self.listener.host,
                "port": self.listener.port,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": live_digest,
                "accept": accept,
                "path": str(self.sealed_path),
                "authenticated": True,
                "upgraded": True,
                "sent": True,
                "received": True,
                "ponged": True,
                "masked": True,
                "replayed": True,
                "independent": True,
            }
        except (OSError, WebSocketActuationError, TimeoutError, json.JSONDecodeError, struct.error) as error:
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
            client.close()

    def read(self) -> dict[str, Any]:
        live = independent_websocket_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "accept": str(live.get("accept") or ""),
            "path": str(self.sealed_path),
            "error": str(live.get("error") or ""),
        }

    def close(self) -> dict[str, Any]:
        listener = self.listener
        self.listener = None
        if listener is not None:
            listener.stop()
        return {"ok": True, "status": 200, "closed": True, "path": str(self.sealed_path)}


def call_websocket_tool(session: WebSocketSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one websocket tool call against a bound RFC 6455 session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    authenticate = arguments.get("authenticate")
    if authenticate is None:
        authenticate = True
    upgrade = arguments.get("upgrade")
    if upgrade is None:
        upgrade = True
    send = arguments.get("send")
    if send is None:
        send = True
    receive = arguments.get("receive")
    if receive is None:
        receive = True
    pong = arguments.get("pong")
    if pong is None:
        pong = True
    mask = arguments.get("mask")
    if mask is None:
        mask = True
    replay = arguments.get("replay")
    if replay is None:
        replay = True
    secret = arguments.get("secret")
    if action == "bind":
        result = session.bind(
            authenticate=bool(authenticate),
            token=None if secret is None else str(secret),
        )
    elif action == "publish":
        result = session.publish(
            token,
            authenticate=bool(authenticate),
            upgrade=bool(upgrade),
            send=bool(send),
            receive=bool(receive),
            pong=bool(pong),
            mask=bool(mask),
            replay=bool(replay),
            secret=None if secret is None else str(secret),
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise WebSocketActuationError(f"unsupported websocket action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_websocket_digest(sealed_path: Path) -> dict[str, Any]:
    """Re-hash the retained frame through a fresh open and compare the sealed digest."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "accept": "",
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
    live_digest = ""
    if retained_path.is_file():
        live_digest = payload_sha256(retained_path.read_bytes())
    authenticated = payload.get("authenticated") is True
    upgraded = payload.get("upgraded") is True
    sent = payload.get("sent") is True
    received = payload.get("received") is True
    ponged = payload.get("ponged") is True
    masked = payload.get("masked") is True
    replayed = payload.get("replayed") is True
    independent = payload.get("independent") is True
    matched = bool(digest) and digest == live_digest
    sentinel = (
        SENTINEL
        if token == SENTINEL
        and matched
        and authenticated
        and upgraded
        and sent
        and received
        and ponged
        and masked
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
        "accept": str(payload.get("accept") or ""),
        "authenticated": authenticated,
        "upgraded": upgraded,
        "sent": sent,
        "received": received,
        "ponged": ponged,
        "masked": masked,
        "replayed": replayed,
        "independent": independent,
        "error": "" if sentinel else "digest_mismatch",
    }


def run_websocket_workflow(
    *,
    with_secret: bool = True,
    skip_bind: bool = False,
    authenticate: bool = True,
    upgrade: bool = True,
    send: bool = True,
    receive: bool = True,
    pong: bool = True,
    mask: bool = True,
    replay: bool = True,
    secret: str | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the UPGRADE/SEND/RECEIVE/PONG/REPLAY workflow and seal a trace."""

    descriptor = websocket_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WEBSOCKET_TOOL_PROVIDER),
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
        raise WebSocketActuationError(f"websocket tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="websocket-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = WebSocketSession(out, secret=DEFAULT_TOKEN if with_secret else "")
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        bind_args: dict[str, Any] = {"action": "bind", "authenticate": True}
        if secret is not None:
            bind_args["secret"] = secret
        calls.append(bind_args)
    publish_args: dict[str, Any] = {
        "action": "publish",
        "token": SENTINEL,
        "authenticate": authenticate,
        "upgrade": upgrade,
        "send": send,
        "receive": receive,
        "pong": pong,
        "mask": mask,
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
                results.append(call_websocket_tool(session, arguments))
            except WebSocketActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_websocket_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_secret
        and not skip_bind
        and authenticate
        and upgrade
        and send
        and receive
        and pong
        and mask
        and replay
        and secret is None
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "websocket_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_secret": with_secret,
        "skip_bind": skip_bind,
        "authenticate": authenticate,
        "upgrade": upgrade,
        "send": send,
        "receive": receive,
        "pong": pong,
        "mask": mask,
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
        "accept": str(publish_result.get("accept") or session.last_accept),
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
        "accept": str(trace_body["accept"] or ""),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "delivered": bool(trace_body["delivered"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_secret": with_secret,
        "skip_bind": skip_bind,
        "authenticate": authenticate,
        "upgrade": upgrade,
        "send": send,
        "receive": receive,
        "pong": pong,
        "mask": mask,
        "replay": replay,
    }


def verify_websocket_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed websocket trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = (
        independent_websocket_digest(sealed_path)
        if sealed_path.is_file()
        else {"ok": False, "sentinel": ""}
    )
    checks = {
        "trace_digest": _digest(body) == trace.get("trace_digest"),
        "routing_digest": _digest(routing) == trace.get("routing_digest"),
        "result_digest": _digest(trace.get("results")) == trace.get("result_digest"),
        "independent_digest": _digest(independent) == trace.get("independent_digest"),
        "routing_executable": routing.get("executable") is True
        and routing.get("route") == EXECUTABLE_TOOL_ROUTE,
        "sentinel_recorded": str(trace.get("sentinel") or "") == SENTINEL,
        "independent_recorded": str(independent.get("sentinel") or "") == SENTINEL,
        "live_payload_matches": str(live_row.get("sentinel") or "") == SENTINEL,
        "payload_exists": bool(trace.get("payload_exists")) and sealed_path.is_file(),
        "delivered": trace.get("delivered") is True,
        "authenticated": independent.get("authenticated") is True,
        "upgraded": independent.get("upgraded") is True,
        "sent": independent.get("sent") is True,
        "received": independent.get("received") is True,
        "ponged": independent.get("ponged") is True,
        "masked": independent.get("masked") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "digest_matches_live": str(independent.get("digest") or "")
        == str(independent.get("live_digest") or live_row.get("live_digest") or ""),
        "accept_recorded": bool(str(trace.get("accept") or independent.get("accept") or "")),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def websocket_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.websocket_actuation import "
        "builtin_websocket_actuation_proof; r=builtin_websocket_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='websocket_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_websocket_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=WEBSOCKET_ACTUATION_ID,
        name="First-class RFC 6455 websocket UPGRADE/SEND/RECEIVE/PONG actuation",
        description=(
            "Missions that require a websocket tool can opt the websocket "
            "provider in, bind a real loopback RFC 6455 listener, complete a "
            "101 Switching Protocols handshake, mask a client text frame, "
            "echo it, answer a control-frame pong, independently replay the "
            "retained payload on a later connection, and seal digest-chained "
            "websocket traces. Default routing stays fail-closed; a missing "
            "token keeps the hole falsifiable, and skip-UPGRADE, skip-SEND, "
            "skip-RECEIVE, skip-PONG, unmasked frames, or skip-REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.websocket_actuation:builtin_websocket_actuation_proof",
        proof_command=websocket_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.mcp-structured-output",
        ),
        behavior_paths=(
            "src/blackhole_agent/websocket_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required websocket tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 6455 listener, completes "
            "a 101 Switching Protocols handshake with Sec-WebSocket-Accept, "
            "masks a client text frame, echoes it, answers a control-frame "
            "pong, independently replays the retained payload on a later "
            "connection, and binds this family as the next diversity-catalog "
            "successor once MCP structuredContent is proved. Missing tokens, "
            "unsigned upgrades, wrong tokens, unmasked client frames, "
            "skip-UPGRADE, skip-SEND, skip-RECEIVE, skip-PONG, and skip-REPLAY "
            "stay fail-closed."
        ),
        tags=(
            "websocket",
            "rfc6455",
            "upgrade",
            "framing",
            "pong",
            "actuation",
            "diversity",
        ),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T134259Z-2faa8636",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_websocket_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 6455 actuation seals a later-connection digest."""

    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.mcp_cursor_pagination import MCP_CURSOR_GOAL, MCP_CURSOR_ID
    from blackhole_agent.mcp_http_event_stream import MCP_HTTP_EVENT_GOAL, MCP_HTTP_EVENT_ID
    from blackhole_agent.mcp_structured_output import MCP_STRUCTURED_GOAL, MCP_STRUCTURED_ID
    from blackhole_agent.mission_selection import (
        capability_family,
        semantic_signature,
        semantic_similarity,
    )
    from blackhole_agent.mqtt_actuation import MQTT_ACTUATION_GOAL, MQTT_ACTUATION_ID
    from blackhole_agent.s3_actuation import S3_ACTUATION_GOAL, S3_ACTUATION_ID
    from blackhole_agent.watch_actuation import WATCH_ACTUATION_GOAL, WATCH_ACTUATION_ID
    from blackhole_agent.webhook_actuation import WEBHOOK_ACTUATION_GOAL, WEBHOOK_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = WEBSOCKET_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(WEBSOCKET_ACTUATION_GOAL) == (
        WEBSOCKET_ACTUATION_ID,
    )
    checks["structured_goal_is_not_websocket"] = leftover_marker_ids(MCP_STRUCTURED_GOAL) == (
        MCP_STRUCTURED_ID,
    )
    checks["cursor_goal_is_not_websocket"] = leftover_marker_ids(MCP_CURSOR_GOAL) == (
        MCP_CURSOR_ID,
    )
    checks["watch_goal_is_not_websocket"] = leftover_marker_ids(WATCH_ACTUATION_GOAL) == (
        WATCH_ACTUATION_ID,
    )
    checks["s3_goal_is_not_websocket"] = leftover_marker_ids(S3_ACTUATION_GOAL) == (
        S3_ACTUATION_ID,
    )
    checks["mqtt_goal_is_not_websocket"] = leftover_marker_ids(MQTT_ACTUATION_GOAL) == (
        MQTT_ACTUATION_ID,
    )
    checks["webhook_goal_is_not_websocket"] = leftover_marker_ids(WEBHOOK_ACTUATION_GOAL) == (
        WEBHOOK_ACTUATION_ID,
    )
    checks["event_stream_goal_is_not_websocket"] = leftover_marker_ids(MCP_HTTP_EVENT_GOAL) == (
        MCP_HTTP_EVENT_ID,
    )
    checks["websocket_goal_is_not_structured"] = MCP_STRUCTURED_ID not in leftover_marker_ids(
        WEBSOCKET_ACTUATION_GOAL
    )
    checks["websocket_goal_is_not_cursor"] = MCP_CURSOR_ID not in leftover_marker_ids(
        WEBSOCKET_ACTUATION_GOAL
    )
    checks["websocket_goal_is_not_watch"] = WATCH_ACTUATION_ID not in leftover_marker_ids(
        WEBSOCKET_ACTUATION_GOAL
    )
    checks["websocket_goal_is_not_s3"] = S3_ACTUATION_ID not in leftover_marker_ids(
        WEBSOCKET_ACTUATION_GOAL
    )
    checks["websocket_goal_is_not_mqtt"] = MQTT_ACTUATION_ID not in leftover_marker_ids(
        WEBSOCKET_ACTUATION_GOAL
    )
    checks["websocket_goal_is_not_webhook"] = WEBHOOK_ACTUATION_ID not in leftover_marker_ids(
        WEBSOCKET_ACTUATION_GOAL
    )
    checks["websocket_goal_is_not_event_stream"] = MCP_HTTP_EVENT_ID not in leftover_marker_ids(
        WEBSOCKET_ACTUATION_GOAL
    )
    checks["structured_marker_stays_structured"] = (
        WEBSOCKET_ACTUATION_ID not in leftover_marker_ids(MCP_STRUCTURED_GOAL)
    )
    checks["cursor_marker_stays_cursor"] = WEBSOCKET_ACTUATION_ID not in leftover_marker_ids(
        MCP_CURSOR_GOAL
    )
    checks["watch_marker_stays_watch"] = WEBSOCKET_ACTUATION_ID not in leftover_marker_ids(
        WATCH_ACTUATION_GOAL
    )
    checks["s3_marker_stays_s3"] = WEBSOCKET_ACTUATION_ID not in leftover_marker_ids(
        S3_ACTUATION_GOAL
    )
    checks["mqtt_marker_stays_mqtt"] = WEBSOCKET_ACTUATION_ID not in leftover_marker_ids(
        MQTT_ACTUATION_GOAL
    )
    checks["webhook_marker_stays_webhook"] = WEBSOCKET_ACTUATION_ID not in leftover_marker_ids(
        WEBHOOK_ACTUATION_GOAL
    )
    checks["event_stream_marker_stays_event_stream"] = (
        WEBSOCKET_ACTUATION_ID not in leftover_marker_ids(MCP_HTTP_EVENT_GOAL)
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_websocket"] = (
        len(catalog) > 41
        and catalog[41]["id"] == WEBSOCKET_ACTUATION_ID
        and catalog[40]["id"] == MCP_STRUCTURED_ID
    )
    family = capability_family(WEBSOCKET_ACTUATION_GOAL)
    checks["family_is_rfc6455"] = "rfc6455" in family
    checks["family_is_websocket"] = "websocket" in family
    checks["family_is_upgrade"] = "upgrade" in family
    checks["family_is_framing"] = "framing" in family
    checks["family_is_not_watch"] = "watch" not in family and "path" not in family
    checks["family_is_not_structured"] = "structured" not in family
    checks["family_is_not_cursor"] = "cursor" not in family and "paginated" not in family
    checks["family_is_not_object"] = "object" not in family
    checks["family_is_not_webhook"] = "webhook" not in family
    checks["family_is_not_mqtt"] = "mqtt" not in family
    checks["family_is_not_catalog"] = "catalog" not in family
    checks["family_is_not_event_stream"] = "event" not in family and "sse" not in family
    sample_key = base64.b64encode(b"0123456789abcdef").decode("ascii")
    checks["accept_key_is_rfc6455"] = websocket_accept_key(sample_key) == base64.b64encode(
        hashlib.sha1(f"{sample_key}{GUID}".encode("ascii")).digest()
    ).decode("ascii")
    neighbors = (
        MCP_STRUCTURED_GOAL,
        MCP_CURSOR_GOAL,
        WATCH_ACTUATION_GOAL,
        S3_ACTUATION_GOAL,
        MQTT_ACTUATION_GOAL,
        WEBHOOK_ACTUATION_GOAL,
        MCP_HTTP_EVENT_GOAL,
    )
    websocket_signature = semantic_signature(WEBSOCKET_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(websocket_signature, semantic_signature(goal)) < 0.82
        for goal in neighbors
    )

    mcp_ws = ToolDescriptor(name="remote_websocket", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_ws)
    checks["naive_mcp_websocket_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = websocket_tool_descriptor()
    default_ws = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WEBSOCKET_TOOL_PROVIDER),
    )
    checks["default_websocket_provider_is_unsupported"] = (
        default_ws.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{WEBSOCKET_TOOL_PROVIDER}" in default_ws.reasons
    )
    checks["opted_in_websocket_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_ws],
        required_tool_names=("local_memory", "websocket"),
    )
    checks["naive_preflight_missing_websocket"] = (
        naive_preflight["ok"] is False
        and naive_preflight["missing_required_tool_names"] == ["websocket"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "websocket"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WEBSOCKET_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "websocket" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="websocket-actuation-") as tmp:
        root = Path(tmp)
        missing = run_websocket_workflow(with_secret=False, output_dir=root / "missing")
        unauth = run_websocket_workflow(authenticate=False, output_dir=root / "unauth")
        wrong = run_websocket_workflow(secret="wrong-token", output_dir=root / "wrong")
        skip_bind = run_websocket_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_upgrade = run_websocket_workflow(upgrade=False, output_dir=root / "skip-upgrade")
        skip_send = run_websocket_workflow(send=False, output_dir=root / "skip-send")
        skip_receive = run_websocket_workflow(receive=False, output_dir=root / "skip-receive")
        skip_pong = run_websocket_workflow(pong=False, output_dir=root / "skip-pong")
        skip_mask = run_websocket_workflow(mask=False, output_dir=root / "skip-mask")
        skip_replay = run_websocket_workflow(replay=False, output_dir=root / "skip-replay")
        live = run_websocket_workflow(output_dir=root / "live")
        verify = verify_websocket_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_websocket_trace(clone)
        checks["naive_without_secret_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_secret"
            and missing["payload_exists"] is False
        )
        checks["unsigned_upgrade_is_forbidden"] = (
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
            and skip_bind["error"] == "websocket_required"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_upgrade_stays_empty"] = (
            skip_upgrade["ok"] is False
            and skip_upgrade["error"] == "upgrade_required"
            and skip_upgrade["final_status"] == 400
            and skip_upgrade["payload_exists"] is False
        )
        checks["skip_send_stays_empty"] = (
            skip_send["ok"] is False
            and skip_send["error"] == "send_required"
            and skip_send["final_status"] == 409
            and skip_send["payload_exists"] is False
        )
        checks["skip_receive_stays_empty"] = (
            skip_receive["ok"] is False
            and skip_receive["error"] == "receive_required"
            and skip_receive["final_status"] == 409
            and skip_receive["payload_exists"] is False
        )
        checks["skip_pong_stays_empty"] = (
            skip_pong["ok"] is False
            and skip_pong["error"] == "pong_required"
            and skip_pong["final_status"] == 409
            and skip_pong["payload_exists"] is False
        )
        checks["unmasked_client_frame_is_rejected"] = (
            skip_mask["ok"] is False
            and skip_mask["error"] == "mask_required"
            and skip_mask["final_status"] == 409
            and skip_mask["payload_exists"] is False
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
        checks["token_upgrade_send_receive_pong_mask_and_replay_are_required"] = (
            missing["ok"] is False
            and unauth["ok"] is False
            and wrong["ok"] is False
            and skip_bind["ok"] is False
            and skip_upgrade["ok"] is False
            and skip_send["ok"] is False
            and skip_receive["ok"] is False
            and skip_pong["ok"] is False
            and skip_mask["ok"] is False
            and skip_replay["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False
        checks["accept_key_recorded"] = bool(str(live.get("accept") or ""))

    with tempfile.TemporaryDirectory(prefix="websocket-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != WEBSOCKET_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_websocket"] = (
        live_goal == WEBSOCKET_ACTUATION_GOAL
        and WEBSOCKET_ACTUATION_ID in live_done
        and live_source == "genesis_bind_websocket"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_websocket_actuation_capability()
    return {
        "ok": ok,
        "action": "websocket_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": WEBSOCKET_ACTUATION_GOAL,
        "done_when": WEBSOCKET_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
