"""Drive a first-class FTP tool through RFC 959 PASV file transfer.

Tool routing already fails missions that require ``ftp``: hosted file-transfer
plugins stay on the unsupported MCP provider, and no first-party FTP
provider is executable. Unbound therefore cannot speak USER/PASS, TYPE I,
PASV, STOR a binary body on a separate data connection, RETR it, or seal a
file digest an independent later session can re-open.

This module closes that hole:

- advertise an ``ftp`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 959 listener
- keep a missing-password client so the USER/PASS hole stays falsifiable
- refuse TYPE/PASV/STOR/RETR until USER/PASS succeed
- refuse STOR until TYPE I plus PASV open a distinct data port
- independently RETR the stored body on a later control session
- persist a sealed file digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after AMQP
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import socket
import socketserver
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
    FTP_TOOL_PROVIDER,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    ftp_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
FTP_ACTUATION_ID = "capability.ftp-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-FTP-OK"
DEFAULT_USERNAME = "blackhole"
DEFAULT_PASSWORD = "blackhole-ftp-secret"
DEFAULT_NAME = "beacon.bin"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
CONTROL_TIMEOUT = 8.0
_PASV_TUPLE = re.compile(r"(\d+),(\d+),(\d+),(\d+),(\d+),(\d+)")

FTP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{FTP_ACTUATION_ID};"
    f"capability_proved:{FTP_ACTUATION_ID};"
    "no_skill_route"
)
FTP_ACTUATION_GOAL = (
    "Repair rfc959 ftpd pasv transfer: hosted ftp tools remain unsupported so "
    "a USER/PASS/PASV/TYPE/STOR/RETR cycle cannot land and a sealed file "
    "digest cannot be produced. A missing ftp password stays forbidden; "
    "fail-closed routing never opts the ftp provider in. The separate data "
    "connection and later-session RETR replay keep the hole falsifiable."
)


class FtpActuationError(RuntimeError):
    """Raised when the FTP session or loopback listener fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def encode_pasv_tuple(host: str, port: int) -> str:
    parts = str(host or "").split(".")
    if len(parts) != 4:
        raise FtpActuationError("pasv_host_invalid")
    try:
        octets = [int(part) for part in parts]
    except ValueError as error:
        raise FtpActuationError("pasv_host_invalid") from error
    if any(octet < 0 or octet > 255 for octet in octets):
        raise FtpActuationError("pasv_host_invalid")
    value = int(port)
    if value < 0 or value > 65535:
        raise FtpActuationError("pasv_port_invalid")
    p1, p2 = divmod(value, 256)
    return ",".join(str(item) for item in (*octets, p1, p2))


def parse_pasv_tuple(text: str) -> tuple[str, int]:
    match = _PASV_TUPLE.search(str(text or ""))
    if match is None:
        raise FtpActuationError("pasv_tuple_required")
    h1, h2, h3, h4, p1, p2 = (int(group) for group in match.groups())
    if any(octet < 0 or octet > 255 for octet in (h1, h2, h3, h4, p1, p2)):
        raise FtpActuationError("pasv_octet_invalid")
    return f"{h1}.{h2}.{h3}.{h4}", p1 * 256 + p2


def format_pasv_reply(host: str, port: int) -> str:
    return f"227 Entering Passive Mode ({encode_pasv_tuple(host, port)})."


class _FtpTCPServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True
    block_on_close = False

    def __init__(
        self,
        address: tuple[str, int],
        handler: type[socketserver.BaseRequestHandler],
        session: FtpSession,
    ) -> None:
        self.session = session
        super().__init__(address, handler)


class _FtpHandler(socketserver.StreamRequestHandler):
    timeout = CONTROL_TIMEOUT

    def _send(self, line: str) -> None:
        self.wfile.write(f"{line}\r\n".encode("ascii", errors="replace"))
        self.wfile.flush()

    def _readline(self) -> str | None:
        raw = self.rfile.readline()
        if not raw:
            return None
        return raw.decode("utf-8", errors="replace").rstrip("\r\n")

    def _close_pasv(self) -> None:
        listener = getattr(self, "_pasv_listener", None)
        self._pasv_listener = None
        if listener is None:
            return
        try:
            listener.close()
        except OSError:
            pass

    def _open_pasv(self) -> int:
        self._close_pasv()
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(IO_TIMEOUT)
        self._pasv_listener = listener
        return int(listener.getsockname()[1])

    def _accept_data(self) -> socket.socket | None:
        listener = getattr(self, "_pasv_listener", None)
        if listener is None:
            return None
        try:
            conn, _address = listener.accept()
        except OSError:
            self._close_pasv()
            return None
        conn.settimeout(IO_TIMEOUT)
        self._close_pasv()
        return conn

    def setup(self) -> None:
        super().setup()
        self._pasv_listener: socket.socket | None = None
        self.logged_in = False
        self.username = ""
        self.binary = False

    def finish(self) -> None:
        self._close_pasv()
        super().finish()

    def handle(self) -> None:
        session: FtpSession = self.server.session  # type: ignore[attr-defined]
        self._send("220 blackhole FTP")
        while True:
            line = self._readline()
            if line is None:
                return
            verb, _, rest = line.partition(" ")
            command = verb.upper()
            argument = rest.strip()
            if command == "USER":
                self.logged_in = False
                self.username = argument
                self._send("331 Password required")
            elif command == "PASS":
                if not self.username:
                    self._send("503 USER first")
                    continue
                if session.credentials_match(self.username, argument):
                    self.logged_in = True
                    self._send("230 Login successful")
                else:
                    self.logged_in = False
                    self._send("530 Login incorrect")
            elif command == "TYPE":
                if not self.logged_in:
                    self._send("530 Please login with USER and PASS")
                    continue
                if argument.upper() != "I":
                    self._send("504 TYPE I required")
                    continue
                self.binary = True
                self._send("200 Type set to I")
            elif command == "PASV":
                if not self.logged_in:
                    self._send("530 Please login with USER and PASS")
                    continue
                if not self.binary:
                    self._send("504 TYPE I required")
                    continue
                port = self._open_pasv()
                self._send(format_pasv_reply("127.0.0.1", port))
            elif command == "STOR":
                self._stor(session, argument)
            elif command == "RETR":
                self._retr(session, argument)
            elif command == "QUIT":
                self._send("221 Goodbye")
                return
            elif command in {"NOOP", "PWD", "SYST"}:
                if command == "SYST":
                    self._send("215 UNIX Type: L8")
                elif command == "PWD":
                    self._send('257 "/"')
                else:
                    self._send("200 OK")
            else:
                self._send("502 Command not implemented")

    def _stor(self, session: FtpSession, name: str) -> None:
        if not self.logged_in:
            self._send("530 Please login with USER and PASS")
            return
        if not self.binary:
            self._send("504 TYPE I required")
            return
        if getattr(self, "_pasv_listener", None) is None:
            self._send("425 PASV required")
            return
        filename = name or DEFAULT_NAME
        self._send("150 Opening BINARY data connection")
        conn = self._accept_data()
        if conn is None:
            self._send("425 Can't open data connection")
            return
        chunks: list[bytes] = []
        try:
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
        except OSError:
            self._send("426 Transfer aborted")
            return
        finally:
            try:
                conn.close()
            except OSError:
                pass
        session.store_file(filename, b"".join(chunks))
        self._send("226 Transfer complete")

    def _retr(self, session: FtpSession, name: str) -> None:
        if not self.logged_in:
            self._send("530 Please login with USER and PASS")
            return
        if not self.binary:
            self._send("504 TYPE I required")
            return
        if getattr(self, "_pasv_listener", None) is None:
            self._send("425 PASV required")
            return
        filename = name or DEFAULT_NAME
        body = session.read_file(filename)
        if body is None:
            self._send("550 File not found")
            return
        self._send("150 Opening BINARY data connection")
        conn = self._accept_data()
        if conn is None:
            self._send("425 Can't open data connection")
            return
        try:
            conn.sendall(body)
            try:
                conn.shutdown(socket.SHUT_WR)
            except OSError:
                pass
        except OSError:
            self._send("426 Transfer aborted")
            return
        finally:
            try:
                conn.close()
            except OSError:
                pass
        self._send("226 Transfer complete")


class _FtpClient:
    def __init__(self, host: str, port: int, *, timeout: float = IO_TIMEOUT) -> None:
        self.host = host
        self.port = int(port)
        self.timeout = timeout
        self.sock = socket.create_connection((host, int(port)), timeout)
        self.sock.settimeout(timeout)
        code, text = self.read_reply()
        if code != 220:
            raise FtpActuationError(f"greeting_required:{code}:{text}")

    def close(self) -> None:
        sock = self.sock
        self.sock = None  # type: ignore[assignment]
        if sock is None:
            return
        try:
            sock.close()
        except OSError:
            pass

    def read_reply(self) -> tuple[int, str]:
        line = self._readline()
        if len(line) < 3 or not line[:3].isdigit():
            raise FtpActuationError(f"malformed_reply:{line!r}")
        code = int(line[:3])
        parts = [line]
        if len(line) > 3 and line[3] == "-":
            prefix = f"{code} "
            while True:
                follow = self._readline()
                parts.append(follow)
                if follow.startswith(prefix):
                    break
        return code, "\n".join(parts)

    def send_cmd(self, line: str) -> tuple[int, str]:
        self.sock.sendall((line + "\r\n").encode("ascii", errors="replace"))
        return self.read_reply()

    def _readline(self) -> str:
        buf = bytearray()
        while True:
            chunk = self.sock.recv(1)
            if not chunk:
                raise FtpActuationError("control_closed")
            buf.extend(chunk)
            if buf.endswith(b"\n"):
                return buf.decode("utf-8", errors="replace").rstrip("\r\n")

    def login(self, username: str, password: str) -> tuple[bool, int, str]:
        code, text = self.send_cmd(f"USER {username}")
        if code != 331:
            return False, code, text
        code, text = self.send_cmd(f"PASS {password}")
        return code == 230, code, text

    def type_i(self) -> tuple[bool, int, str]:
        code, text = self.send_cmd("TYPE I")
        return code == 200, code, text

    def pasv(self) -> tuple[bool, int, str, str, int]:
        code, text = self.send_cmd("PASV")
        if code != 227:
            return False, code, text, "", 0
        host, port = parse_pasv_tuple(text)
        return True, code, text, host, port

    def stor(self, name: str, body: bytes, data_host: str, data_port: int) -> tuple[bool, int, str]:
        data = socket.create_connection((data_host, int(data_port)), self.timeout)
        data.settimeout(self.timeout)
        try:
            code, text = self.send_cmd(f"STOR {name}")
            if code != 150:
                return False, code, text
            data.sendall(body)
            try:
                data.shutdown(socket.SHUT_WR)
            except OSError:
                pass
        finally:
            try:
                data.close()
            except OSError:
                pass
        code, text = self.read_reply()
        return code == 226, code, text

    def retr(self, name: str, data_host: str, data_port: int) -> tuple[bool, int, str, bytes]:
        data = socket.create_connection((data_host, int(data_port)), self.timeout)
        data.settimeout(self.timeout)
        chunks: list[bytes] = []
        try:
            code, text = self.send_cmd(f"RETR {name}")
            if code != 150:
                return False, code, text, b""
            while True:
                chunk = data.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
        finally:
            try:
                data.close()
            except OSError:
                pass
        code, text = self.read_reply()
        body = b"".join(chunks)
        return code == 226, code, text, body

    def quit(self) -> None:
        try:
            self.send_cmd("QUIT")
        except (OSError, FtpActuationError):
            pass


class FtpSession:
    """Credential-gated loopback RFC 959 listener: bind, publish, read."""

    def __init__(self, output_dir: Path, *, password: str = DEFAULT_PASSWORD, user: str = DEFAULT_USERNAME) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.user = str(user or "")
        self.password = str(password or "")
        self.host: str | None = None
        self.port: int | None = None
        self.server: _FtpTCPServer | None = None
        self.thread: threading.Thread | None = None
        self.files: dict[str, bytes] = {}
        self.stored = False
        self.retrieved = False
        self.replayed = False
        self.last_token = ""
        self.last_digest = ""
        self.last_data_port = 0
        self.history: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    @property
    def sealed_path(self) -> Path:
        return self.output_dir / SEALED_NAME

    def credentials_match(self, user: str, password: str) -> bool:
        if not self.password:
            return False
        return bool(user) and user == self.user and password == self.password

    def store_file(self, name: str, body: bytes) -> None:
        with self._lock:
            self.files[str(name or DEFAULT_NAME)] = bytes(body or b"")
            self.stored = True

    def read_file(self, name: str) -> bytes | None:
        with self._lock:
            if str(name or DEFAULT_NAME) not in self.files:
                return None
            return self.files[str(name or DEFAULT_NAME)]

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "data_port": 0,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": 409,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "data_port": 0,
            "stored": self.stored,
        }

    def bind(self) -> dict[str, Any]:
        if not self.password:
            return self._forbidden("missing_secret")
        if self.server is not None:
            return {
                "ok": True,
                "status": 200,
                "host": self.host or "",
                "port": int(self.port or 0),
                "reused": True,
            }
        server = _FtpTCPServer(("127.0.0.1", 0), _FtpHandler, self)
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True)
        thread.start()
        host, port = server.server_address[:2]
        self.server = server
        self.thread = thread
        self.host = str(host)
        self.port = int(port)
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
        authenticate: bool = True,
        type_binary: bool = True,
        pasv: bool = True,
        store: bool = True,
        retrieve: bool = True,
        replay: bool = True,
        password: str | None = None,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if not self.password:
            return self._forbidden("missing_secret")
        live_token = str(token or SENTINEL)
        body = live_token.encode("utf-8")
        secret = self.password if password is None else str(password)
        client: _FtpClient | None = None
        independent: _FtpClient | None = None
        try:
            client = _FtpClient(self.host, int(self.port))
            if authenticate:
                ok, code, _text = client.login(self.user, secret)
                if not ok:
                    status = 403 if code == 530 else int(code or 530)
                    reason = "auth_failed" if password is not None or code == 530 else "login_required"
                    if password is not None:
                        reason = "auth_failed"
                    return self._forbidden(reason, status=status)
            if type_binary:
                ok, code, _text = client.type_i()
                if not ok:
                    reason = "login_required" if code == 530 else "type_required"
                    status = 530 if code == 530 else 409
                    return self._forbidden(reason, status=status) if code == 530 else self._conflict(reason)
            elif store or retrieve or pasv:
                return self._conflict("type_required")
            data_host = ""
            data_port = 0
            if store:
                if not pasv:
                    return self._conflict("pasv_required")
                ok, code, _text, data_host, data_port = client.pasv()
                if not ok:
                    reason = "login_required" if code == 530 else "pasv_required"
                    status = 530 if code == 530 else 409
                    return self._forbidden(reason, status=status) if code == 530 else self._conflict(reason)
                if data_port == int(self.port or 0):
                    return self._conflict("data_port_collision")
                self.last_data_port = int(data_port)
                ok, code, _text = client.stor(DEFAULT_NAME, body, data_host, data_port)
                if not ok:
                    reason = {
                        530: "login_required",
                        504: "type_required",
                        425: "pasv_required",
                    }.get(code, "store_required")
                    if code == 530:
                        return self._forbidden(reason, status=530)
                    return self._conflict(reason)
            elif retrieve or replay:
                return self._conflict("store_required")
            retrieved_body = b""
            if retrieve:
                ok, code, _text, data_host, data_port = client.pasv()
                if not ok:
                    return self._conflict("pasv_required")
                ok, code, _text, retrieved_body = client.retr(DEFAULT_NAME, data_host, data_port)
                if not ok or retrieved_body != body:
                    return self._conflict("retrieve_required")
                self.retrieved = True
            elif replay:
                return self._conflict("retrieve_required")
            try:
                client.quit()
            except FtpActuationError:
                pass
            client.close()
            client = None
            if replay:
                independent = _FtpClient(self.host, int(self.port))
                ok, _code, _text = independent.login(self.user, self.password)
                if not ok:
                    return self._forbidden("independent_login_failed", status=503)
                ok, _code, _text = independent.type_i()
                if not ok:
                    return self._conflict("independent_type_failed")
                ok, _code, _text, data_host, data_port = independent.pasv()
                if not ok:
                    return self._conflict("independent_pasv_failed")
                ok, _code, _text, replay_body = independent.retr(DEFAULT_NAME, data_host, data_port)
                if not ok or replay_body != body:
                    return self._conflict("replay_required")
                self.replayed = True
                try:
                    independent.quit()
                except FtpActuationError:
                    pass
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(body)
            sealed = {
                "name": DEFAULT_NAME,
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(body),
                "control_port": int(self.port or 0),
                "data_port": int(self.last_data_port),
                "login": True,
                "typed": True,
                "pasv": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "authenticated": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_ftp_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "name": DEFAULT_NAME,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(body),
                "control_port": int(self.port or 0),
                "data_port": int(self.last_data_port),
                "path": str(self.sealed_path),
                "authenticated": True,
                "login": True,
                "typed": True,
                "pasv": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
            }
        except (OSError, FtpActuationError) as error:
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
        live = independent_ftp_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "name": str(live.get("name") or ""),
            "data_port": int(live.get("data_port") or 0),
            "path": str(self.sealed_path),
            "error": str(live.get("error") or ""),
        }

    def close(self) -> dict[str, Any]:
        server = self.server
        thread = self.thread
        self.server = None
        self.thread = None
        self.host = None
        self.port = None
        if server is not None:
            try:
                server.shutdown()
            except OSError:
                pass
            try:
                server.server_close()
            except OSError:
                pass
        if thread is not None:
            thread.join(timeout=1)
        return {"ok": True, "status": 200, "closed": True, "path": str(self.sealed_path)}


def call_ftp_tool(session: FtpSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one FTP tool call against a bound listener session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    authenticate = True if arguments.get("authenticate") is None else bool(arguments.get("authenticate"))
    type_binary = True if arguments.get("type") is None else bool(arguments.get("type"))
    pasv = True if arguments.get("pasv") is None else bool(arguments.get("pasv"))
    store = True if arguments.get("store") is None else bool(arguments.get("store"))
    retrieve = True if arguments.get("retrieve") is None else bool(arguments.get("retrieve"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    password = arguments.get("password")
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            authenticate=authenticate,
            type_binary=type_binary,
            pasv=pasv,
            store=store,
            retrieve=retrieve,
            replay=replay,
            password=None if password is None else str(password),
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise FtpActuationError(f"unsupported ftp action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_ftp_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed FTP file through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "name": "",
        "data_port": 0,
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
            "login",
            "typed",
            "pasv",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "authenticated",
        )
    )
    control_port = int(payload.get("control_port") or 0)
    data_port = int(payload.get("data_port") or 0)
    dual = data_port > 0 and control_port > 0 and data_port != control_port
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "name": str(payload.get("name") or ""),
        "size": int(payload.get("size") or 0),
        "control_port": control_port,
        "data_port": data_port,
        "login": payload.get("login") is True,
        "typed": payload.get("typed") is True,
        "pasv": payload.get("pasv") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "authenticated": payload.get("authenticated") is True,
    }


def run_ftp_workflow(
    *,
    with_secret: bool = True,
    skip_bind: bool = False,
    authenticate: bool = True,
    type_binary: bool = True,
    pasv: bool = True,
    store: bool = True,
    retrieve: bool = True,
    replay: bool = True,
    password: str | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 959 PASV file-transfer workflow and seal a trace."""

    descriptor = ftp_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, FTP_TOOL_PROVIDER),
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
        raise FtpActuationError(f"ftp tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="ftp-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = FtpSession(out, password=DEFAULT_PASSWORD if with_secret else "")
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    publish_args: dict[str, Any] = {
        "action": "publish",
        "token": SENTINEL,
        "authenticate": authenticate,
        "type": type_binary,
        "pasv": pasv,
        "store": store,
        "retrieve": retrieve,
        "replay": replay,
    }
    if password is not None:
        publish_args["password"] = password
    calls.append(publish_args)
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_ftp_tool(session, arguments))
            except FtpActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_ftp_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_secret
        and not skip_bind
        and authenticate
        and type_binary
        and pasv
        and store
        and retrieve
        and replay
        and password is None
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "ftp_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_secret": with_secret,
        "skip_bind": skip_bind,
        "authenticate": authenticate,
        "type": type_binary,
        "pasv": pasv,
        "store": store,
        "retrieve": retrieve,
        "replay": replay,
        "wrong_password": password is not None,
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
        "data_port": int(publish_result.get("data_port") or independent.get("data_port") or 0),
        "control_port": int(publish_result.get("control_port") or independent.get("control_port") or 0),
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
        "data_port": int(trace_body["data_port"] or 0),
        "control_port": int(trace_body["control_port"] or 0),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_secret": with_secret,
        "skip_bind": skip_bind,
        "authenticate": authenticate,
        "type": type_binary,
        "pasv": pasv,
        "store": store,
        "retrieve": retrieve,
        "replay": replay,
    }


def verify_ftp_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed FTP trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_ftp_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    control_port = int(trace.get("control_port") or independent.get("control_port") or 0)
    data_port = int(trace.get("data_port") or independent.get("data_port") or 0)
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
        "login": independent.get("login") is True,
        "typed": independent.get("typed") is True,
        "pasv": independent.get("pasv") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "authenticated": independent.get("authenticated") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "dual_channel": data_port > 0 and control_port > 0 and data_port != control_port,
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def ftp_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.ftp_actuation import "
        "builtin_ftp_actuation_proof; r=builtin_ftp_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='ftp_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_ftp_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=FTP_ACTUATION_ID,
        name="First-class RFC 959 FTP PASV file-transfer actuation",
        description=(
            "Missions that require an ftp tool can opt the ftp provider in, "
            "bind a loopback RFC 959 listener, complete USER/PASS, TYPE I, "
            "PASV, STOR a binary body on a separate data connection, RETR it "
            "on the same session, independently RETR the stored body on a "
            "later control session, and seal a digest-chained file transfer. "
            "Default routing stays fail-closed; a missing USER/PASS password "
            "keeps the hole falsifiable, and skip-TYPE/PASV/STOR/RETR/REPLAY "
            "stay empty."
        ),
        kind="python",
        entry="blackhole_agent.ftp_actuation:builtin_ftp_actuation_proof",
        proof_command=ftp_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.amqp-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/ftp_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required ftp tool is executable after explicit provider opt-in: "
            "Unbound binds a real loopback RFC 959 listener, speaks USER/PASS, "
            "TYPE I, PASV, STOR a binary body on a distinct data port, RETR "
            "it, independently RETR the stored body on a later control "
            "session, and binds this family as the next diversity-catalog "
            "successor once AMQP 0-9-1 work-queue delivery is proved. Missing "
            "credentials, skip-TYPE, skip-PASV, skip-STOR, skip-RETR, and "
            "skip-REPLAY stay fail-closed."
        ),
        tags=("ftp", "rfc959", "pasv", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T161531Z-2a088007",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_ftp_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 959 FTP PASV actuation seals a file digest."""

    from blackhole_agent.amqp_actuation import AMQP_ACTUATION_GOAL, AMQP_ACTUATION_ID
    from blackhole_agent.grpc_actuation import GRPC_ACTUATION_GOAL, GRPC_ACTUATION_ID
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
    from blackhole_agent.s3_actuation import S3_ACTUATION_GOAL, S3_ACTUATION_ID
    from blackhole_agent.smtp_actuation import SMTP_ACTUATION_GOAL, SMTP_ACTUATION_ID
    from blackhole_agent.ssh_actuation import SSH_ACTUATION_GOAL, SSH_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = FTP_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(FTP_ACTUATION_GOAL) == (FTP_ACTUATION_ID,)
    checks["amqp_goal_is_not_ftp"] = leftover_marker_ids(AMQP_ACTUATION_GOAL) == (AMQP_ACTUATION_ID,)
    checks["grpc_goal_is_not_ftp"] = leftover_marker_ids(GRPC_ACTUATION_GOAL) == (GRPC_ACTUATION_ID,)
    checks["ssh_goal_is_not_ftp"] = leftover_marker_ids(SSH_ACTUATION_GOAL) == (SSH_ACTUATION_ID,)
    checks["smtp_goal_is_not_ftp"] = leftover_marker_ids(SMTP_ACTUATION_GOAL) == (SMTP_ACTUATION_ID,)
    checks["s3_goal_is_not_ftp"] = leftover_marker_ids(S3_ACTUATION_GOAL) == (S3_ACTUATION_ID,)
    checks["ftp_goal_is_not_amqp"] = AMQP_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    checks["ftp_goal_is_not_grpc"] = GRPC_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    checks["ftp_goal_is_not_ssh"] = SSH_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    checks["ftp_goal_is_not_smtp"] = SMTP_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    checks["ftp_goal_is_not_s3"] = S3_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    checks["amqp_marker_stays_amqp"] = FTP_ACTUATION_ID not in leftover_marker_ids(AMQP_ACTUATION_GOAL)
    checks["grpc_marker_stays_grpc"] = FTP_ACTUATION_ID not in leftover_marker_ids(GRPC_ACTUATION_GOAL)
    checks["ssh_marker_stays_ssh"] = FTP_ACTUATION_ID not in leftover_marker_ids(SSH_ACTUATION_GOAL)
    checks["smtp_marker_stays_smtp"] = FTP_ACTUATION_ID not in leftover_marker_ids(SMTP_ACTUATION_GOAL)
    checks["s3_marker_stays_s3"] = FTP_ACTUATION_ID not in leftover_marker_ids(S3_ACTUATION_GOAL)
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_ftp"] = (
        len(catalog) > 45
        and catalog[45]["id"] == FTP_ACTUATION_ID
        and catalog[44]["id"] == AMQP_ACTUATION_ID
    )
    family = capability_family(FTP_ACTUATION_GOAL)
    checks["family_is_ftp"] = "ftpd" in family
    checks["family_is_pasv"] = "pasv" in family
    checks["family_is_rfc959"] = "rfc959" in family
    checks["family_is_transfer"] = "transfer" in family
    checks["family_is_not_amqp"] = "amqp" not in family and "queue" not in family
    checks["family_is_not_grpc"] = "grpc" not in family and "http2" not in family
    checks["family_is_not_openssh"] = "openssh" not in family and "ssh" not in family
    checks["family_is_not_smtp"] = "smtp" not in family
    checks["family_is_not_s3"] = "object" not in family and "putobject" not in family
    packed = encode_pasv_tuple("127.0.0.1", 196 + 256 * 20)
    host, port = parse_pasv_tuple(f"227 Entering Passive Mode ({packed}).")
    checks["pasv_tuple_roundtrip"] = host == "127.0.0.1" and port == 196 + 256 * 20 and packed == "127,0,0,1,20,196"
    checks["pasv_reply_contains_tuple"] = encode_pasv_tuple("127.0.0.1", 2121) in format_pasv_reply("127.0.0.1", 2121)
    neighbors = (
        AMQP_ACTUATION_GOAL,
        GRPC_ACTUATION_GOAL,
        SSH_ACTUATION_GOAL,
        SMTP_ACTUATION_GOAL,
        S3_ACTUATION_GOAL,
    )
    ftp_signature = semantic_signature(FTP_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(ftp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_ftp = ToolDescriptor(name="remote_ftp", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_ftp)
    checks["naive_mcp_ftp_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = ftp_tool_descriptor()
    default_ftp = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, FTP_TOOL_PROVIDER),
    )
    checks["default_ftp_provider_is_unsupported"] = (
        default_ftp.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{FTP_TOOL_PROVIDER}" in default_ftp.reasons
    )
    checks["opted_in_ftp_is_executable"] = opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_ftp],
        required_tool_names=("local_memory", "ftp"),
    )
    checks["naive_preflight_missing_ftp"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["ftp"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "ftp"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, FTP_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "ftp" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="ftp-actuation-") as tmp:
        root = Path(tmp)
        missing = run_ftp_workflow(with_secret=False, output_dir=root / "missing")
        unauth = run_ftp_workflow(authenticate=False, output_dir=root / "unauth")
        wrong = run_ftp_workflow(password="wrong-password", output_dir=root / "wrong")
        skip_bind = run_ftp_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_type = run_ftp_workflow(type_binary=False, output_dir=root / "skip-type")
        skip_pasv = run_ftp_workflow(pasv=False, output_dir=root / "skip-pasv")
        skip_store = run_ftp_workflow(store=False, output_dir=root / "skip-store")
        skip_retr = run_ftp_workflow(retrieve=False, output_dir=root / "skip-retr")
        skip_replay = run_ftp_workflow(replay=False, output_dir=root / "skip-replay")
        live = run_ftp_workflow(output_dir=root / "live")
        verify = verify_ftp_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_ftp_trace(clone)
        checks["naive_without_secret_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_secret"
            and missing["payload_exists"] is False
        )
        checks["unauthenticated_transfer_is_forbidden"] = (
            unauth["ok"] is False
            and unauth["final_status"] == 530
            and unauth["error"] == "login_required"
            and unauth["payload_exists"] is False
        )
        checks["wrong_password_is_forbidden"] = (
            wrong["ok"] is False
            and wrong["final_status"] == 403
            and wrong["error"] == "auth_failed"
            and wrong["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_type_stays_empty"] = (
            skip_type["ok"] is False
            and skip_type["error"] == "type_required"
            and skip_type["final_status"] == 409
            and skip_type["payload_exists"] is False
        )
        checks["skip_pasv_stays_empty"] = (
            skip_pasv["ok"] is False
            and skip_pasv["error"] == "pasv_required"
            and skip_pasv["final_status"] == 409
            and skip_pasv["payload_exists"] is False
        )
        checks["skip_store_stays_empty"] = (
            skip_store["ok"] is False
            and skip_store["error"] == "store_required"
            and skip_store["final_status"] == 409
            and skip_store["payload_exists"] is False
        )
        checks["skip_retr_stays_empty"] = (
            skip_retr["ok"] is False
            and skip_retr["error"] == "retrieve_required"
            and skip_retr["final_status"] == 409
            and skip_retr["payload_exists"] is False
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
        checks["workflow_records_dual_channel"] = (
            int(live.get("data_port") or 0) > 0
            and int(live.get("control_port") or 0) > 0
            and int(live.get("data_port") or 0) != int(live.get("control_port") or 0)
        )
        checks["token_login_type_pasv_store_retr_and_replay_are_required"] = (
            missing["ok"] is False
            and unauth["ok"] is False
            and wrong["ok"] is False
            and skip_bind["ok"] is False
            and skip_type["ok"] is False
            and skip_pasv["ok"] is False
            and skip_store["ok"] is False
            and skip_retr["ok"] is False
            and skip_replay["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="ftp-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != FTP_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_ftp"] = (
        live_goal == FTP_ACTUATION_GOAL
        and FTP_ACTUATION_ID in live_done
        and live_source == "genesis_bind_ftp"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_ftp_actuation_capability()
    return {
        "ok": ok,
        "action": "ftp_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": FTP_ACTUATION_GOAL,
        "done_when": FTP_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
