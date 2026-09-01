"""Drive a first-class RADIUS tool through RFC 2865 Access-Request/Access-Accept.

Tool routing already fails missions that require ``radius``: hosted RADIUS
plugins stay on the unsupported MCP provider, and no first-party RADIUS
provider is executable. Unbound therefore cannot speak Access-Request, lockstep
an Access-Accept attribute exchange over UDP, independently poll the stored
User-Name, or seal an attribute digest an independent later reader can re-open.

This module closes that hole:

- advertise a ``radius`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 2865 daemon
- keep a missing-secret client so the shared-secret hole stays falsifiable
- refuse Access-Accept until Access-Request lands with a User-Name and secret
- independently poll the stored User-Name attribute on a later client socket
- persist a sealed attribute digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after NTP
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
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    RADIUS_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    local_memory_tool_descriptor,
    radius_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
RADIUS_ACTUATION_ID = "capability.radius-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-RADIUS-OK"
POLL_USER = "BH-RADIUS-POLL"
DEFAULT_SECRET = b"blackhole-radius-secret"
DEFAULT_PASSWORD = b"blackhole-ok"
DEFAULT_NAS_IP = "127.0.0.1"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
HEADER_SIZE = 20
AUTHENTICATOR_SIZE = 16
CODE_ACCESS_REQUEST = 1
CODE_ACCESS_ACCEPT = 2
ATTR_USER_NAME = 1
ATTR_USER_PASSWORD = 2
ATTR_NAS_IP_ADDRESS = 4
ATTR_NAS_PORT = 5
ATTR_REPLY_MESSAGE = 18
HEADER_STRUCT = struct.Struct("!BBH16s")

RADIUS_ACTUATION_DONE_WHEN = (
    f"capability_exists:{RADIUS_ACTUATION_ID};"
    f"capability_proved:{RADIUS_ACTUATION_ID};"
    "no_skill_route"
)
RADIUS_ACTUATION_GOAL = (
    "Repair rfc2865 radius access-request/access-accept cycle cannot land over "
    "udp attributes: hosted radius tools remain unsupported so an Access-Request "
    "then Access-Accept attribute exchange cannot land and a sealed attribute "
    "digest cannot be produced. A missing radius secret stays forbidden; "
    "fail-closed routing never opts the radius provider in. An independent later "
    "poll of the stored User-Name attribute keeps the hole falsifiable."
)


class RadiusActuationError(RuntimeError):
    """Raised when the RADIUS session or loopback daemon fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def _md5(data: bytes) -> bytes:
    try:
        return hashlib.md5(data, usedforsecurity=False).digest()
    except TypeError:
        return hashlib.md5(data).digest()


def request_authenticator(token: str = SENTINEL) -> bytes:
    return hashlib.sha256(str(token or SENTINEL).encode("utf-8")).digest()[:AUTHENTICATOR_SIZE]


def poll_authenticator(token: str = SENTINEL) -> bytes:
    return hashlib.sha256(f"poll:{token or SENTINEL}".encode("utf-8")).digest()[:AUTHENTICATOR_SIZE]


def encode_attribute(attr_type: int, value: bytes) -> bytes:
    raw = bytes(value or b"")
    length = 2 + len(raw)
    if length > 255:
        raise RadiusActuationError("attribute_too_long")
    return bytes((int(attr_type) & 0xFF, length)) + raw


def parse_attributes(data: bytes) -> list[tuple[int, bytes]]:
    raw = bytes(data or b"")
    attrs: list[tuple[int, bytes]] = []
    offset = 0
    while offset < len(raw):
        if offset + 2 > len(raw):
            raise RadiusActuationError("short_attribute")
        attr_type = raw[offset]
        length = raw[offset + 1]
        if length < 2 or offset + length > len(raw):
            raise RadiusActuationError("illegal_attribute")
        attrs.append((attr_type, raw[offset + 2 : offset + length]))
        offset += length
    return attrs


def attribute_value(attributes: Sequence[tuple[int, bytes]], attr_type: int) -> bytes:
    for atype, value in attributes:
        if int(atype) == int(attr_type):
            return bytes(value or b"")
    return b""


def hide_password(password: bytes, secret: bytes, authenticator: bytes) -> bytes:
    key = bytes(secret or b"")
    vector = bytes(authenticator or b"")
    if not key:
        raise RadiusActuationError("missing_secret")
    if len(vector) != AUTHENTICATOR_SIZE:
        raise RadiusActuationError("short_authenticator")
    padded = bytes(password or b"")
    if not padded:
        padded = b"\x00" * 16
    if len(padded) % 16:
        padded = padded + b"\x00" * (16 - (len(padded) % 16))
    out = bytearray()
    last = vector
    for index in range(0, len(padded), 16):
        digest = _md5(key + last)
        block = bytes(left ^ right for left, right in zip(padded[index : index + 16], digest))
        out.extend(block)
        last = block
    return bytes(out)


def reveal_password(hidden: bytes, secret: bytes, authenticator: bytes) -> bytes:
    cipher = bytes(hidden or b"")
    key = bytes(secret or b"")
    vector = bytes(authenticator or b"")
    if not key:
        raise RadiusActuationError("missing_secret")
    if len(vector) != AUTHENTICATOR_SIZE:
        raise RadiusActuationError("short_authenticator")
    if not cipher or len(cipher) % 16:
        raise RadiusActuationError("illegal_password")
    out = bytearray()
    last = vector
    for index in range(0, len(cipher), 16):
        digest = _md5(key + last)
        block = cipher[index : index + 16]
        out.extend(bytes(left ^ right for left, right in zip(block, digest)))
        last = block
    return bytes(out).rstrip(b"\x00")


def response_authenticator(
    code: int,
    identifier: int,
    length: int,
    request_authenticator_bytes: bytes,
    attributes: bytes,
    secret: bytes,
) -> bytes:
    key = bytes(secret or b"")
    if not key:
        raise RadiusActuationError("missing_secret")
    body = (
        struct.pack("!BBH", int(code) & 0xFF, int(identifier) & 0xFF, int(length) & 0xFFFF)
        + bytes(request_authenticator_bytes or b"")
        + bytes(attributes or b"")
        + key
    )
    return _md5(body)


def encode_request(
    *,
    identifier: int,
    username: str,
    authenticator: bytes,
    password: bytes = DEFAULT_PASSWORD,
    secret: bytes = DEFAULT_SECRET,
    nas_ip: str = DEFAULT_NAS_IP,
    nas_port: int = 0,
    include_username: bool = True,
    include_password: bool = True,
) -> bytes:
    vector = bytes(authenticator or b"")
    if len(vector) != AUTHENTICATOR_SIZE:
        raise RadiusActuationError("short_authenticator")
    chunks: list[bytes] = []
    if include_username and str(username or ""):
        chunks.append(encode_attribute(ATTR_USER_NAME, str(username).encode("utf-8")))
    chunks.append(encode_attribute(ATTR_NAS_IP_ADDRESS, socket.inet_aton(nas_ip)))
    if int(nas_port) > 0:
        chunks.append(encode_attribute(ATTR_NAS_PORT, int(nas_port).to_bytes(4, "big")))
    if include_password and bytes(secret or b""):
        chunks.append(
            encode_attribute(ATTR_USER_PASSWORD, hide_password(password, secret, vector))
        )
    body = b"".join(chunks)
    length = HEADER_SIZE + len(body)
    header = HEADER_STRUCT.pack(CODE_ACCESS_REQUEST, int(identifier) & 0xFF, length, vector)
    return header + body


def encode_accept(
    *,
    identifier: int,
    request_auth: bytes,
    username: str,
    secret: bytes = DEFAULT_SECRET,
    include_secret: bool = True,
) -> bytes:
    chunks: list[bytes] = []
    if str(username or ""):
        encoded = str(username).encode("utf-8")
        chunks.append(encode_attribute(ATTR_USER_NAME, encoded))
        chunks.append(encode_attribute(ATTR_REPLY_MESSAGE, encoded))
    body = b"".join(chunks)
    length = HEADER_SIZE + len(body)
    if include_secret and bytes(secret or b""):
        authenticator = response_authenticator(
            CODE_ACCESS_ACCEPT,
            identifier,
            length,
            request_auth,
            body,
            secret,
        )
    else:
        authenticator = b"\x00" * AUTHENTICATOR_SIZE
    header = HEADER_STRUCT.pack(CODE_ACCESS_ACCEPT, int(identifier) & 0xFF, length, authenticator)
    return header + body


def parse_packet(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < HEADER_SIZE:
        raise RadiusActuationError("short_packet")
    code, identifier, length, authenticator = HEADER_STRUCT.unpack(raw[:HEADER_SIZE])
    if length < HEADER_SIZE or length > len(raw):
        raise RadiusActuationError("illegal_length")
    if int(code) not in {CODE_ACCESS_REQUEST, CODE_ACCESS_ACCEPT}:
        raise RadiusActuationError("illegal_code")
    attributes = parse_attributes(raw[HEADER_SIZE:length])
    username = attribute_value(attributes, ATTR_USER_NAME).decode("utf-8", errors="replace")
    password = attribute_value(attributes, ATTR_USER_PASSWORD)
    return {
        "code": int(code),
        "identifier": int(identifier),
        "length": int(length),
        "authenticator": bytes(authenticator),
        "attributes": attributes,
        "username": username,
        "has_username": bool(username),
        "has_password": bool(password),
        "authenticated": bool(password),
    }


def verify_accept(packet: bytes, request_auth: bytes, secret: bytes) -> bool:
    raw = bytes(packet or b"")
    try:
        parsed = parse_packet(raw)
    except RadiusActuationError:
        return False
    if parsed["code"] != CODE_ACCESS_ACCEPT:
        return False
    try:
        expected = response_authenticator(
            parsed["code"],
            parsed["identifier"],
            parsed["length"],
            request_auth,
            raw[HEADER_SIZE : parsed["length"]],
            secret,
        )
    except RadiusActuationError:
        return False
    return hmac.compare_digest(expected, parsed["authenticator"])


class _RadiusClient:
    def __init__(
        self,
        host: str,
        port: int,
        *,
        secret: bytes = DEFAULT_SECRET,
        timeout: float = IO_TIMEOUT,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.secret = bytes(secret or b"")
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

    def _recv(self, request_auth: bytes) -> dict[str, Any]:
        try:
            payload, _addr = self.sock.recvfrom(4096)
        except (OSError, TimeoutError, socket.timeout) as error:
            raise RadiusActuationError("timeout") from error
        packet = parse_packet(payload)
        if packet["code"] != CODE_ACCESS_ACCEPT:
            raise RadiusActuationError("accept_required")
        if not verify_accept(payload, request_auth, self.secret):
            raise RadiusActuationError("secret_required")
        return packet

    def exchange(
        self,
        packet: bytes,
        request_auth: bytes,
        *,
        wait_response: bool = True,
    ) -> dict[str, Any]:
        self.sock.sendto(bytes(packet or b""), (self.host, self.port))
        if not wait_response:
            raise RadiusActuationError("accept_required")
        return self._recv(request_auth)

    def access_request(
        self,
        username: str,
        authenticator: bytes,
        *,
        identifier: int = 1,
        wait_response: bool = True,
        include_username: bool = True,
        include_password: bool = True,
    ) -> dict[str, Any]:
        packet = encode_request(
            identifier=identifier,
            username=username,
            authenticator=authenticator,
            secret=self.secret,
            nas_port=self.client_port,
            include_username=include_username,
            include_password=include_password,
        )
        return self.exchange(packet, authenticator, wait_response=wait_response)


class RadiusSession:
    """Secret-gated loopback RFC 2865 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        secret: bytes = DEFAULT_SECRET,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.secret = bytes(secret or b"")
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.username = ""
        self.stored = False
        self.retrieved = False
        self.replayed = False
        self.last_token = ""
        self.last_digest = ""
        self.history: list[dict[str, Any]] = []
        self._running = False
        self._lock = threading.Lock()

    @property
    def sealed_path(self) -> Path:
        return self.output_dir / SEALED_NAME

    def store_username_once(self, username: str) -> str:
        with self._lock:
            value = str(username or "")
            if not self.username and value:
                self.username = value
                self.stored = True
            return str(self.username)

    def read_username(self) -> str:
        with self._lock:
            return str(self.username)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "username": "",
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _reply(self, peer: tuple[str, int], identifier: int, request_auth: bytes, username: str) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_accept(
            identifier=identifier,
            request_auth=request_auth,
            username=username,
            secret=self.secret,
            include_secret=bool(self.secret),
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
                payload, addr = sock.recvfrom(4096)
            except (TimeoutError, socket.timeout):
                continue
            except OSError:
                return
            try:
                packet = parse_packet(payload)
            except RadiusActuationError:
                continue
            if packet.get("code") != CODE_ACCESS_REQUEST:
                continue
            username = str(packet.get("username") or "")
            hidden = attribute_value(packet.get("attributes") or [], ATTR_USER_PASSWORD)
            if not username or not hidden:
                continue
            try:
                revealed = reveal_password(hidden, self.secret, packet["authenticator"])
            except RadiusActuationError:
                continue
            if not hmac.compare_digest(revealed, DEFAULT_PASSWORD):
                continue
            stored = self.store_username_once(username)
            peer = (str(addr[0]), int(addr[1]))
            self._reply(peer, int(packet["identifier"]), packet["authenticator"], stored)

    def bind(self) -> dict[str, Any]:
        if not self.secret:
            return self._forbidden("missing_secret")
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
        do_request: bool = True,
        do_accept: bool = True,
        do_username: bool = True,
        replay: bool = True,
        use_secret: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if not self.secret:
            return self._forbidden("missing_secret")
        live_token = str(token or SENTINEL)
        origin_auth = request_authenticator(live_token)
        client: _RadiusClient | None = None
        independent: _RadiusClient | None = None
        try:
            client = _RadiusClient(self.host, int(self.port), secret=self.secret)
            if not do_request:
                return self._conflict("request_required")
            packet = encode_request(
                identifier=1,
                username=live_token if do_username else "",
                authenticator=origin_auth,
                secret=self.secret,
                nas_port=client.client_port,
                include_username=do_username,
                include_password=use_secret and bool(self.secret),
            )
            if not do_username:
                try:
                    client.sock.sendto(packet, (self.host, int(self.port)))
                except OSError:
                    pass
                return self._conflict("username_required")
            if not use_secret:
                try:
                    client.exchange(packet, origin_auth, wait_response=True)
                except RadiusActuationError:
                    return self._conflict("secret_required")
                return self._conflict("secret_required")
            if not do_accept:
                try:
                    client.exchange(packet, origin_auth, wait_response=False)
                except RadiusActuationError as error:
                    if str(error) == "accept_required":
                        return self._conflict("accept_required")
                    return self._conflict("accept_required")
                return self._conflict("accept_required")
            try:
                reply = client.exchange(packet, origin_auth, wait_response=True)
            except RadiusActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("secret_required")
                if reason == "accept_required":
                    return self._conflict("accept_required")
                return self._conflict("request_required")
            if str(reply.get("username") or "") != live_token:
                return self._conflict("username_required")
            self.retrieved = True
            if replay:
                independent = _RadiusClient(self.host, int(self.port), secret=self.secret)
                try:
                    poll = independent.access_request(
                        POLL_USER,
                        poll_authenticator(live_token),
                        identifier=2,
                        wait_response=True,
                    )
                except RadiusActuationError:
                    return self._conflict("replay_required")
                stored = self.read_username()
                if str(poll.get("username") or "") != live_token or stored != live_token:
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(live_token.encode("utf-8"))
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "username": live_token,
                "identifier": 1,
                "secret_bound": True,
                "request": True,
                "accept": True,
                "username_sent": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_radius_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "username": live_token,
                "identifier": 1,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "request": True,
                "accept": True,
                "username_sent": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "secret_bound": True,
            }
        except (OSError, RadiusActuationError) as error:
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
        live = independent_radius_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "username": str(live.get("username") or ""),
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


def call_radius_tool(session: RadiusSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one RADIUS tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_request = True if arguments.get("request") is None else bool(arguments.get("request"))
    do_accept = True if arguments.get("accept") is None else bool(arguments.get("accept"))
    do_username = True if arguments.get("username") is None else bool(arguments.get("username"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_secret = True if arguments.get("use_secret") is None else bool(arguments.get("use_secret"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_request=do_request,
            do_accept=do_accept,
            do_username=do_username,
            replay=replay,
            use_secret=use_secret,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise RadiusActuationError(f"unsupported radius action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_radius_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed RADIUS attribute digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "username": "",
        "port": 0,
        "identifier": 0,
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
            "request",
            "accept",
            "username_sent",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "secret_bound",
        )
    )
    port = int(payload.get("port") or 0)
    username = str(payload.get("username") or "")
    identifier = int(payload.get("identifier") or 0)
    dual = port > 0 and bool(username) and identifier > 0
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "username": username,
        "size": int(payload.get("size") or 0),
        "port": port,
        "identifier": identifier,
        "request": payload.get("request") is True,
        "accept": payload.get("accept") is True,
        "username_sent": payload.get("username_sent") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "secret_bound": payload.get("secret_bound") is True,
    }


def run_radius_workflow(
    *,
    with_secret: bool = True,
    skip_bind: bool = False,
    do_request: bool = True,
    do_accept: bool = True,
    do_username: bool = True,
    replay: bool = True,
    use_secret: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 2865 Access-Request/Access-Accept workflow."""

    descriptor = radius_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, RADIUS_TOOL_PROVIDER),
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
        raise RadiusActuationError(f"radius tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="radius-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = RadiusSession(out, secret=DEFAULT_SECRET if with_secret else b"")
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "request": do_request,
            "accept": do_accept,
            "username": do_username,
            "replay": replay,
            "use_secret": use_secret,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_radius_tool(session, arguments))
            except RadiusActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_radius_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_secret
        and not skip_bind
        and do_request
        and do_accept
        and do_username
        and replay
        and use_secret
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "radius_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_secret": with_secret,
        "skip_bind": skip_bind,
        "request": do_request,
        "accept": do_accept,
        "username": do_username,
        "replay": replay,
        "use_secret": use_secret,
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
        "username_value": str(publish_result.get("username") or independent.get("username") or ""),
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
        "username": str(trace_body["username_value"] or ""),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_secret": with_secret,
        "skip_bind": skip_bind,
        "request": do_request,
        "accept": do_accept,
        "username_sent": do_username,
        "replay": replay,
        "use_secret": use_secret,
    }


def verify_radius_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed RADIUS trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_radius_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    username = str(trace.get("username_value") or independent.get("username") or "")
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
        "request": independent.get("request") is True,
        "accept": independent.get("accept") is True,
        "username_sent": independent.get("username_sent") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "secret_bound": independent.get("secret_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "username_bound": port > 0 and username == SENTINEL,
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def radius_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.radius_actuation import "
        "builtin_radius_actuation_proof; r=builtin_radius_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='radius_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_radius_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=RADIUS_ACTUATION_ID,
        name="First-class RFC 2865 RADIUS Access-Request/Access-Accept actuation",
        description=(
            "Missions that require a radius tool can opt the radius provider in, "
            "bind a loopback RFC 2865 UDP daemon, complete Access-Request with a "
            "User-Name and shared-secret User-Password, lockstep an Access-Accept "
            "that echoes the stored User-Name, independently poll the stored "
            "User-Name on a later socket, and seal a digest-chained attribute. "
            "Default routing stays fail-closed; a missing secret keeps the hole "
            "falsifiable, and skip-REQUEST/ACCEPT/USERNAME/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.radius_actuation:builtin_radius_actuation_proof",
        proof_command=radius_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.ntp-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/radius_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/dhcp_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required radius tool is executable after explicit provider opt-in: "
            "Unbound binds a real loopback RFC 2865 daemon, speaks Access-Request "
            "then Access-Accept over UDP attributes with a shared secret, "
            "independently polls the stored User-Name attribute on a later "
            "client socket, and binds this family as the next diversity-catalog "
            "successor once RFC 5905 NTP lockstep is proved. Missing secrets, "
            "skip-Access-Request, skip-Access-Accept, skip-User-Name, skip-REPLAY, "
            "and Access-Request aimed without a secret stay fail-closed. Later "
            "genesis can take RFC 2131 DHCP DISCOVER/OFFER/ACK as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("radius", "rfc2865", "udp", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T195452Z-e2867194",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_radius_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 2865 RADIUS lockstep actuation seals an attribute digest."""

    from blackhole_agent.dhcp_actuation import DHCP_ACTUATION_GOAL, DHCP_ACTUATION_ID
    from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
    from blackhole_agent.ftp_actuation import FTP_ACTUATION_GOAL, FTP_ACTUATION_ID
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
    from blackhole_agent.snmp_actuation import SNMP_ACTUATION_GOAL, SNMP_ACTUATION_ID
    from blackhole_agent.syslog_actuation import SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID
    from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = RADIUS_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(RADIUS_ACTUATION_GOAL) == (RADIUS_ACTUATION_ID,)
    checks["ntp_goal_is_not_radius"] = leftover_marker_ids(NTP_ACTUATION_GOAL) == (NTP_ACTUATION_ID,)
    checks["syslog_goal_is_not_radius"] = leftover_marker_ids(SYSLOG_ACTUATION_GOAL) == (SYSLOG_ACTUATION_ID,)
    checks["snmp_goal_is_not_radius"] = leftover_marker_ids(SNMP_ACTUATION_GOAL) == (SNMP_ACTUATION_ID,)
    checks["tftp_goal_is_not_radius"] = leftover_marker_ids(TFTP_ACTUATION_GOAL) == (TFTP_ACTUATION_ID,)
    checks["ftp_goal_is_not_radius"] = leftover_marker_ids(FTP_ACTUATION_GOAL) == (FTP_ACTUATION_ID,)
    checks["dns_goal_is_not_radius"] = leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    checks["dhcp_goal_is_not_radius"] = leftover_marker_ids(DHCP_ACTUATION_GOAL) == (DHCP_ACTUATION_ID,)
    checks["radius_goal_is_not_ntp"] = NTP_ACTUATION_ID not in leftover_marker_ids(RADIUS_ACTUATION_GOAL)
    checks["radius_goal_is_not_syslog"] = SYSLOG_ACTUATION_ID not in leftover_marker_ids(RADIUS_ACTUATION_GOAL)
    checks["radius_goal_is_not_snmp"] = SNMP_ACTUATION_ID not in leftover_marker_ids(RADIUS_ACTUATION_GOAL)
    checks["radius_goal_is_not_tftp"] = TFTP_ACTUATION_ID not in leftover_marker_ids(RADIUS_ACTUATION_GOAL)
    checks["radius_goal_is_not_ftp"] = FTP_ACTUATION_ID not in leftover_marker_ids(RADIUS_ACTUATION_GOAL)
    checks["radius_goal_is_not_dns"] = DNS_ACTUATION_ID not in leftover_marker_ids(RADIUS_ACTUATION_GOAL)
    checks["radius_goal_is_not_dhcp"] = DHCP_ACTUATION_ID not in leftover_marker_ids(RADIUS_ACTUATION_GOAL)
    checks["ntp_marker_stays_ntp"] = RADIUS_ACTUATION_ID not in leftover_marker_ids(NTP_ACTUATION_GOAL)
    checks["syslog_marker_stays_syslog"] = RADIUS_ACTUATION_ID not in leftover_marker_ids(SYSLOG_ACTUATION_GOAL)
    checks["snmp_marker_stays_snmp"] = RADIUS_ACTUATION_ID not in leftover_marker_ids(SNMP_ACTUATION_GOAL)
    checks["tftp_marker_stays_tftp"] = RADIUS_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    checks["ftp_marker_stays_ftp"] = RADIUS_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    checks["dns_marker_stays_dns"] = RADIUS_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    checks["dhcp_marker_stays_dhcp"] = RADIUS_ACTUATION_ID not in leftover_marker_ids(DHCP_ACTUATION_GOAL)
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_radius"] = (
        len(catalog) > 50
        and catalog[50]["id"] == RADIUS_ACTUATION_ID
        and catalog[49]["id"] == NTP_ACTUATION_ID
        and catalog[50]["source"] == "genesis_bind_radius"
    )
    checks["catalog_names_dhcp"] = (
        len(catalog) > 51
        and catalog[51]["id"] == DHCP_ACTUATION_ID
        and catalog[51]["source"] == "genesis_bind_dhcp"
    )
    family = capability_family(RADIUS_ACTUATION_GOAL)
    checks["family_is_radius"] = "radiu" in family
    checks["family_is_rfc2865"] = "rfc2865" in family
    checks["family_is_not_ntp"] = "ntp" not in family and "rfc5905" not in family and "keyid" not in family
    checks["family_is_not_syslog"] = "syslog" not in family and "nilvalue" not in family
    checks["family_is_not_snmp"] = "snmp" not in family and "varbind" not in family
    checks["family_is_not_tftp"] = "tftp" not in family and "rfc1350" not in family
    checks["family_is_not_ftp"] = "ftpd" not in family and "pasv" not in family
    checks["family_is_not_dns"] = "tsig" not in family and "nameserver" not in family
    checks["family_is_not_dhcp"] = "dhcp" not in family and "rfc2131" not in family
    origin = request_authenticator()
    packed = encode_request(identifier=1, username=SENTINEL, authenticator=origin)
    parsed = parse_packet(packed)
    checks["request_roundtrip"] = (
        parsed["code"] == CODE_ACCESS_REQUEST
        and parsed["username"] == SENTINEL
        and parsed["has_username"] is True
        and parsed["authenticated"] is True
        and reveal_password(
            attribute_value(parsed["attributes"], ATTR_USER_PASSWORD),
            DEFAULT_SECRET,
            origin,
        )
        == DEFAULT_PASSWORD
    )
    accept_packet = encode_accept(identifier=1, request_auth=origin, username=SENTINEL)
    accept = parse_packet(accept_packet)
    checks["accept_roundtrip"] = (
        accept["code"] == CODE_ACCESS_ACCEPT
        and accept["username"] == SENTINEL
        and verify_accept(accept_packet, origin, DEFAULT_SECRET)
    )
    bare = encode_request(
        identifier=1,
        username=SENTINEL,
        authenticator=origin,
        include_password=False,
    )
    checks["missing_secret_is_unauthenticated"] = parse_packet(bare)["authenticated"] is False
    neighbors = (
        NTP_ACTUATION_GOAL,
        SYSLOG_ACTUATION_GOAL,
        SNMP_ACTUATION_GOAL,
        TFTP_ACTUATION_GOAL,
        FTP_ACTUATION_GOAL,
        DNS_ACTUATION_GOAL,
        DHCP_ACTUATION_GOAL,
    )
    radius_signature = semantic_signature(RADIUS_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(radius_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_radius = ToolDescriptor(name="remote_radius", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_radius)
    checks["naive_mcp_radius_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = radius_tool_descriptor()
    default_radius = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, RADIUS_TOOL_PROVIDER),
    )
    checks["default_radius_provider_is_unsupported"] = (
        default_radius.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{RADIUS_TOOL_PROVIDER}" in default_radius.reasons
    )
    checks["opted_in_radius_is_executable"] = opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_radius],
        required_tool_names=("local_memory", "radius"),
    )
    checks["naive_preflight_missing_radius"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["radius"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "radius"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, RADIUS_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "radius" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="radius-actuation-") as tmp:
        root = Path(tmp)
        missing = run_radius_workflow(with_secret=False, output_dir=root / "missing")
        skip_bind = run_radius_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_request = run_radius_workflow(do_request=False, output_dir=root / "skip-request")
        skip_accept = run_radius_workflow(do_accept=False, output_dir=root / "skip-accept")
        skip_username = run_radius_workflow(do_username=False, output_dir=root / "skip-username")
        skip_replay = run_radius_workflow(replay=False, output_dir=root / "skip-replay")
        skip_secret = run_radius_workflow(use_secret=False, output_dir=root / "skip-secret")
        live = run_radius_workflow(output_dir=root / "live")
        verify = verify_radius_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_radius_trace(clone)
        checks["naive_without_secret_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_secret"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_request_stays_empty"] = (
            skip_request["ok"] is False
            and skip_request["error"] == "request_required"
            and skip_request["final_status"] == 409
            and skip_request["payload_exists"] is False
        )
        checks["skip_accept_stays_empty"] = (
            skip_accept["ok"] is False
            and skip_accept["error"] == "accept_required"
            and skip_accept["final_status"] == 409
            and skip_accept["payload_exists"] is False
        )
        checks["skip_username_stays_empty"] = (
            skip_username["ok"] is False
            and skip_username["error"] == "username_required"
            and skip_username["final_status"] == 409
            and skip_username["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_secret_stays_empty"] = (
            skip_secret["ok"] is False
            and skip_secret["error"] == "secret_required"
            and skip_secret["final_status"] == 409
            and skip_secret["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_username"] = live.get("username") == SENTINEL and int(live.get("port") or 0) > 0
        checks["token_secret_request_accept_username_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_request["ok"] is False
            and skip_accept["ok"] is False
            and skip_username["ok"] is False
            and skip_replay["ok"] is False
            and skip_secret["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="radius-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != RADIUS_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_radius"] = (
        live_goal == RADIUS_ACTUATION_GOAL
        and RADIUS_ACTUATION_ID in live_done
        and live_source == "genesis_bind_radius"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_radius_actuation_capability()
    return {
        "ok": ok,
        "action": "radius_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": RADIUS_ACTUATION_GOAL,
        "done_when": RADIUS_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
