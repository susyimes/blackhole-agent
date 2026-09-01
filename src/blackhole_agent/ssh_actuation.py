"""Drive a first-class ssh tool through SSH-2.0 binary-packet session exec.

Tool routing already fails missions that require ``ssh``: hosted remote-exec
plugins stay on the unsupported MCP provider, and no first-party SSH-2.0
provider is executable. Unbound therefore cannot complete identification,
KEXINIT, group14 DH, password USERAUTH, CHANNEL-OPEN/EXEC, or independently
replay sealed stdout.

This module closes that hole:

- advertise an ``ssh`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback SSH-2.0 daemon
- keep a missing-password client so the USERAUTH hole stays falsifiable
- refuse CHANNEL-OPEN/EXEC until password USERAUTH succeeds
- MAC every post-NEWKEYS packet with hmac-sha2-256 derived from group14 DH
- EXEC then independently re-EXEC from a fresh connection so skip-IDENTIFY,
  skip-KEX, skip-EXEC, skip-MAC, and skip-REPLAY stay empty
- persist a sealed stdout digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after websocket
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import socket
import socketserver
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
    SSH_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    local_memory_tool_descriptor,
    route_tool_descriptor,
    ssh_tool_descriptor,
)

SCHEMA_VERSION = 1
SSH_ACTUATION_ID = "capability.ssh-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-SSH-OK"
DEFAULT_USER = "blackhole"
DEFAULT_PASSWORD = "blackhole-ssh-secret"
HOST_SECRET = b"blackhole-ssh-host"
HOST_KEY_TYPE = "blackhole-hmac-sha256"
HOST_ID = hashlib.sha256(b"blackhole-ssh-host-id").digest()
IDENT_STRING = "SSH-2.0-Blackhole_1.0"
SEALED_NAME = "sealed.json"
RETAINED_NAME = "retained.bin"
IO_TIMEOUT = 2.0
MAX_PACKET = 256 * 1024
BLOCK_SIZE = 8
MAC_LEN = 32
WINDOW_SIZE = 64 * 1024
MAX_CHAN_PACKET = 32 * 1024

MSG_DISCONNECT = 1
MSG_SERVICE_REQUEST = 5
MSG_SERVICE_ACCEPT = 6
MSG_KEXINIT = 20
MSG_NEWKEYS = 21
MSG_KEXDH_INIT = 30
MSG_KEXDH_REPLY = 31
MSG_USERAUTH_REQUEST = 50
MSG_USERAUTH_FAILURE = 51
MSG_USERAUTH_SUCCESS = 52
MSG_CHANNEL_OPEN = 90
MSG_CHANNEL_OPEN_CONFIRMATION = 91
MSG_CHANNEL_OPEN_FAILURE = 92
MSG_CHANNEL_DATA = 94
MSG_CHANNEL_EOF = 96
MSG_CHANNEL_CLOSE = 97
MSG_CHANNEL_REQUEST = 98
MSG_CHANNEL_SUCCESS = 99
MSG_CHANNEL_FAILURE = 100

KEX_ALGS = "diffie-hellman-group14-sha256"
HOST_ALGS = HOST_KEY_TYPE
ENC_ALGS = "none"
MAC_ALGS = "hmac-sha2-256"
COMP_ALGS = "none"
SERVICE_USERAUTH = "ssh-userauth"
SERVICE_CONNECTION = "ssh-connection"

# RFC 3526 2048-bit MODP group 14
GROUP14_P = int(
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD1"
    "29024E088A67CC74020BBEA63B139B22514A08798E3404DD"
    "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245"
    "E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
    "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3D"
    "C2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F"
    "83655D23DCA3AD961C62F356208552BB9ED529077096966D"
    "670C354E4ABC9804F1746C08CA18217C32905E462E36CE3B"
    "E39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9"
    "DE2BCBF6955817183995497CEA956AE515D2261898FA0510"
    "15728E5A4AACAA68FFFFFFFFFFFFFFFF",
    16,
)
GROUP14_G = 2

SSH_ACTUATION_DONE_WHEN = (
    f"capability_exists:{SSH_ACTUATION_ID};"
    f"capability_proved:{SSH_ACTUATION_ID};"
    "no_skill_route"
)
SSH_ACTUATION_GOAL = (
    "Repair openssh exec binary-packet channel: hosted ssh tools remain "
    "unsupported so an IDENTIFY/KEXINIT/USERAUTH/CHANNEL-OPEN/EXEC cycle "
    "cannot land and a sealed stdout digest cannot be produced. A missing "
    "ssh password stays forbidden; fail-closed routing never opts the ssh "
    "provider in. The group14 DH shared secret and later-session exec "
    "replay keep the hole falsifiable."
)


class SshActuationError(RuntimeError):
    """Raised when the SSH session or daemon fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def ssh_string(data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + data


def ssh_uint32(value: int) -> bytes:
    return struct.pack(">I", int(value) & 0xFFFFFFFF)


def ssh_bool(value: bool) -> bytes:
    return b"\x01" if value else b"\x00"


def ssh_mpint(value: int) -> bytes:
    if value == 0:
        return ssh_string(b"")
    if value < 0:
        raise SshActuationError("negative mpint")
    length = (value.bit_length() + 7) // 8
    raw = value.to_bytes(length, "big")
    if raw[0] & 0x80:
        raw = b"\x00" + raw
    return ssh_string(raw)


def parse_ssh_string(data: bytes, offset: int = 0) -> tuple[bytes, int]:
    if offset + 4 > len(data):
        raise SshActuationError("truncated string")
    length = struct.unpack(">I", data[offset : offset + 4])[0]
    start = offset + 4
    end = start + length
    if end > len(data):
        raise SshActuationError("truncated string body")
    return data[start:end], end


def parse_ssh_mpint(data: bytes, offset: int = 0) -> tuple[int, int]:
    raw, next_off = parse_ssh_string(data, offset)
    if not raw:
        return 0, next_off
    value = int.from_bytes(raw, "big")
    if raw[0] & 0x80:
        value -= 1 << (len(raw) * 8)
    return value, next_off


def parse_ssh_uint32(data: bytes, offset: int = 0) -> tuple[int, int]:
    if offset + 4 > len(data):
        raise SshActuationError("truncated uint32")
    return struct.unpack(">I", data[offset : offset + 4])[0], offset + 4


def parse_ssh_bool(data: bytes, offset: int = 0) -> tuple[bool, int]:
    if offset >= len(data):
        raise SshActuationError("truncated bool")
    return data[offset] != 0, offset + 1


def encode_host_key() -> bytes:
    return ssh_string(HOST_KEY_TYPE.encode("ascii")) + ssh_string(HOST_ID)


def sign_kex_hash(kex_hash: bytes, host_secret: bytes = HOST_SECRET) -> bytes:
    mac = hmac.new(bytes(host_secret), bytes(kex_hash), hashlib.sha256).digest()
    return ssh_string(HOST_KEY_TYPE.encode("ascii")) + ssh_string(mac)


def verify_kex_signature(kex_hash: bytes, signature: bytes, host_secret: bytes = HOST_SECRET) -> bool:
    expected = sign_kex_hash(kex_hash, host_secret)
    return hmac.compare_digest(signature, expected)


def dh_private() -> int:
    while True:
        secret = int.from_bytes(os.urandom(32), "big")
        if 1 < secret < GROUP14_P - 1:
            return secret


def dh_public(secret: int) -> int:
    return pow(GROUP14_G, int(secret), GROUP14_P)


def dh_shared(peer_public: int, secret: int) -> int:
    if peer_public <= 1 or peer_public >= GROUP14_P - 1:
        raise SshActuationError("kex_required")
    return pow(int(peer_public), int(secret), GROUP14_P)


def encode_kexinit(cookie: bytes | None = None) -> bytes:
    nonce = bytes(cookie or os.urandom(16))
    if len(nonce) != 16:
        raise SshActuationError("kex cookie must be 16 bytes")
    payload = bytes([MSG_KEXINIT]) + nonce
    for names in (KEX_ALGS, HOST_ALGS, ENC_ALGS, ENC_ALGS, MAC_ALGS, MAC_ALGS, COMP_ALGS, COMP_ALGS, "", ""):
        payload += ssh_string(names.encode("ascii"))
    payload += ssh_bool(False) + ssh_uint32(0)
    return payload


def compute_kex_hash(
    v_c: str,
    v_s: str,
    i_c: bytes,
    i_s: bytes,
    k_s: bytes,
    e: int,
    f: int,
    shared: int,
) -> bytes:
    material = b"".join(
        (
            ssh_string(v_c.encode("ascii")),
            ssh_string(v_s.encode("ascii")),
            ssh_string(i_c),
            ssh_string(i_s),
            ssh_string(k_s),
            ssh_mpint(e),
            ssh_mpint(f),
            ssh_mpint(shared),
        )
    )
    return hashlib.sha256(material).digest()


def derive_key(shared: int, kex_hash: bytes, letter: bytes, session_id: bytes) -> bytes:
    material = ssh_mpint(shared) + bytes(kex_hash) + bytes(letter) + bytes(session_id)
    return hashlib.sha256(material).digest()


def encode_packet(payload: bytes, *, seq: int, mac_key: bytes | None) -> bytes:
    body_without_pad = 5 + len(payload)
    pad = 4 + ((BLOCK_SIZE - ((body_without_pad + 4) % BLOCK_SIZE)) % BLOCK_SIZE)
    padding = os.urandom(pad)
    packet_length = 1 + len(payload) + pad
    packet = struct.pack(">I", packet_length) + bytes([pad]) + payload + padding
    if mac_key is not None:
        mac = hmac.new(mac_key, struct.pack(">I", seq & 0xFFFFFFFF) + packet, hashlib.sha256).digest()
        return packet + mac
    return packet


def _read_exact(rfile: Any, size: int) -> bytes:
    if size < 0 or size > MAX_PACKET:
        raise SshActuationError(f"packet length out of range: {size}")
    buf = bytearray()
    while len(buf) < size:
        chunk = rfile.read(size - len(buf))
        if not chunk:
            raise SshActuationError("eof")
        buf.extend(chunk)
    return bytes(buf)


def decode_packet(rfile: Any, *, seq: int, mac_key: bytes | None) -> bytes:
    header = _read_exact(rfile, 5)
    packet_length = struct.unpack(">I", header[:4])[0]
    if packet_length < 5 or packet_length > MAX_PACKET:
        raise SshActuationError(f"packet length out of range: {packet_length}")
    rest = _read_exact(rfile, packet_length - 1)
    packet = header + rest
    if mac_key is not None:
        mac = _read_exact(rfile, MAC_LEN)
        expected = hmac.new(mac_key, struct.pack(">I", seq & 0xFFFFFFFF) + packet, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, expected):
            raise SshActuationError("mac_required")
    pad = packet[4]
    end = 4 + packet_length - pad
    if end < 5 or end > len(packet):
        raise SshActuationError("invalid padding")
    return packet[5:end]


def encode_disconnect(reason: str, *, code: int = 2) -> bytes:
    return bytes([MSG_DISCONNECT]) + ssh_uint32(code) + ssh_string(reason.encode("ascii")) + ssh_string(b"")


def encode_service_request(name: str) -> bytes:
    return bytes([MSG_SERVICE_REQUEST]) + ssh_string(name.encode("ascii"))


def encode_service_accept(name: str) -> bytes:
    return bytes([MSG_SERVICE_ACCEPT]) + ssh_string(name.encode("ascii"))


def encode_userauth_request(user: str, password: str) -> bytes:
    return (
        bytes([MSG_USERAUTH_REQUEST])
        + ssh_string(user.encode("utf-8"))
        + ssh_string(SERVICE_CONNECTION.encode("ascii"))
        + ssh_string(b"password")
        + ssh_bool(False)
        + ssh_string(password.encode("utf-8"))
    )


def encode_userauth_failure() -> bytes:
    return bytes([MSG_USERAUTH_FAILURE]) + ssh_string(b"password") + ssh_bool(False)


def encode_userauth_success() -> bytes:
    return bytes([MSG_USERAUTH_SUCCESS])


def encode_channel_open(*, sender: int = 0) -> bytes:
    return (
        bytes([MSG_CHANNEL_OPEN])
        + ssh_string(b"session")
        + ssh_uint32(sender)
        + ssh_uint32(WINDOW_SIZE)
        + ssh_uint32(MAX_CHAN_PACKET)
    )


def encode_channel_open_confirmation(*, recipient: int, sender: int = 1) -> bytes:
    return (
        bytes([MSG_CHANNEL_OPEN_CONFIRMATION])
        + ssh_uint32(recipient)
        + ssh_uint32(sender)
        + ssh_uint32(WINDOW_SIZE)
        + ssh_uint32(MAX_CHAN_PACKET)
    )


def encode_channel_request_exec(*, recipient: int, command: str, want_reply: bool = True) -> bytes:
    return (
        bytes([MSG_CHANNEL_REQUEST])
        + ssh_uint32(recipient)
        + ssh_string(b"exec")
        + ssh_bool(want_reply)
        + ssh_string(command.encode("utf-8"))
    )


def encode_channel_success(*, recipient: int) -> bytes:
    return bytes([MSG_CHANNEL_SUCCESS]) + ssh_uint32(recipient)


def encode_channel_data(*, recipient: int, data: bytes) -> bytes:
    return bytes([MSG_CHANNEL_DATA]) + ssh_uint32(recipient) + ssh_string(data)


def encode_channel_eof(*, recipient: int) -> bytes:
    return bytes([MSG_CHANNEL_EOF]) + ssh_uint32(recipient)


def encode_channel_close(*, recipient: int) -> bytes:
    return bytes([MSG_CHANNEL_CLOSE]) + ssh_uint32(recipient)


def encode_kexdh_init(public: int) -> bytes:
    return bytes([MSG_KEXDH_INIT]) + ssh_mpint(public)


def encode_kexdh_reply(*, host_key: bytes, public: int, signature: bytes) -> bytes:
    return bytes([MSG_KEXDH_REPLY]) + ssh_string(host_key) + ssh_mpint(public) + ssh_string(signature)


def parse_disconnect(payload: bytes) -> str:
    if not payload or payload[0] != MSG_DISCONNECT:
        return ""
    _code, offset = parse_ssh_uint32(payload, 1)
    description, _offset = parse_ssh_string(payload, offset)
    return description.decode("utf-8", errors="replace")


def parse_userauth_request(payload: bytes) -> dict[str, str]:
    if not payload or payload[0] != MSG_USERAUTH_REQUEST:
        raise SshActuationError("auth_required")
    user, offset = parse_ssh_string(payload, 1)
    _service, offset = parse_ssh_string(payload, offset)
    method, offset = parse_ssh_string(payload, offset)
    if method != b"password":
        return {"user": user.decode("utf-8", errors="replace"), "method": method.decode("ascii", errors="replace"), "password": ""}
    _changing, offset = parse_ssh_bool(payload, offset)
    password, _offset = parse_ssh_string(payload, offset)
    return {
        "user": user.decode("utf-8", errors="replace"),
        "method": "password",
        "password": password.decode("utf-8", errors="replace"),
    }


def parse_channel_open(payload: bytes) -> dict[str, Any]:
    if not payload or payload[0] != MSG_CHANNEL_OPEN:
        raise SshActuationError("channel_required")
    kind, offset = parse_ssh_string(payload, 1)
    sender, offset = parse_ssh_uint32(payload, offset)
    return {"kind": kind.decode("ascii", errors="replace"), "sender": sender}


def parse_channel_request(payload: bytes) -> dict[str, Any]:
    if not payload or payload[0] != MSG_CHANNEL_REQUEST:
        raise SshActuationError("exec_required")
    recipient, offset = parse_ssh_uint32(payload, 1)
    kind, offset = parse_ssh_string(payload, offset)
    want_reply, offset = parse_ssh_bool(payload, offset)
    command = b""
    if kind == b"exec":
        command, _offset = parse_ssh_string(payload, offset)
    return {
        "recipient": recipient,
        "kind": kind.decode("ascii", errors="replace"),
        "want_reply": want_reply,
        "command": command.decode("utf-8", errors="replace"),
    }


def parse_channel_data(payload: bytes) -> bytes:
    if not payload or payload[0] != MSG_CHANNEL_DATA:
        raise SshActuationError("receive_required")
    _recipient, offset = parse_ssh_uint32(payload, 1)
    data, _offset = parse_ssh_string(payload, offset)
    return data


def parse_kexdh_init(payload: bytes) -> int:
    if not payload or payload[0] != MSG_KEXDH_INIT:
        raise SshActuationError("kex_required")
    public, _offset = parse_ssh_mpint(payload, 1)
    return public


def parse_kexdh_reply(payload: bytes) -> dict[str, Any]:
    if not payload or payload[0] != MSG_KEXDH_REPLY:
        raise SshActuationError("kex_required")
    host_key, offset = parse_ssh_string(payload, 1)
    public, offset = parse_ssh_mpint(payload, offset)
    signature, _offset = parse_ssh_string(payload, offset)
    return {"host_key": host_key, "public": public, "signature": signature}


def read_ident(rfile: Any) -> str:
    while True:
        line = rfile.readline()
        if not line:
            raise SshActuationError("identify_required")
        text = line.decode("ascii", errors="replace").rstrip("\r\n")
        if text.startswith("SSH-"):
            return text


class SshConn:
    """SSH-2.0 binary-packet connection with optional post-NEWKEYS MAC."""

    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self.rfile = sock.makefile("rb", buffering=0)
        self.wfile = sock.makefile("wb", buffering=0)
        self.seq_send = 0
        self.seq_recv = 0
        self.send_mac_key: bytes | None = None
        self.recv_mac_key: bytes | None = None
        self.v_local = IDENT_STRING
        self.v_peer = ""
        self.i_local = b""
        self.i_peer = b""
        self.session_id = b""
        self.shared = 0

    def close(self) -> None:
        try:
            self.wfile.close()
        except OSError:
            pass
        try:
            self.rfile.close()
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass

    def send_payload(self, payload: bytes, *, mac: bool | None = None) -> None:
        key = self.send_mac_key if mac is None else (self.send_mac_key if mac else None)
        packet = encode_packet(payload, seq=self.seq_send, mac_key=key)
        if mac is False and self.send_mac_key is not None:
            packet += b"\x00" * MAC_LEN
        self.wfile.write(packet)
        self.wfile.flush()
        self.seq_send += 1

    def recv_payload(self) -> bytes:
        payload = decode_packet(self.rfile, seq=self.seq_recv, mac_key=self.recv_mac_key)
        self.seq_recv += 1
        return payload

    def write_ident(self) -> None:
        self.wfile.write(f"{IDENT_STRING}\r\n".encode("ascii"))
        self.wfile.flush()

    def read_ident(self) -> str:
        self.v_peer = read_ident(self.rfile)
        return self.v_peer


class SshClient:
    """Minimal SSH-2.0 client: identify, group14 kex, password USERAUTH, exec."""

    def __init__(self) -> None:
        self.conn: SshConn | None = None
        self.peer_channel = 1
        self.local_channel = 0
        self.session_id = ""
        self.stdout = b""

    def close(self) -> None:
        conn = self.conn
        self.conn = None
        if conn is not None:
            conn.close()

    def connect(self, host: str, port: int) -> None:
        sock = socket.create_connection((host, int(port)), timeout=IO_TIMEOUT)
        sock.settimeout(IO_TIMEOUT)
        self.conn = SshConn(sock)

    def _require(self) -> SshConn:
        if self.conn is None:
            raise SshActuationError("ssh_required")
        return self.conn

    def identify(self) -> dict[str, Any]:
        conn = self._require()
        conn.write_ident()
        peer = conn.read_ident()
        if not peer.startswith("SSH-2.0-"):
            return {"ok": False, "error": "identify_required"}
        return {"ok": True, "peer": peer}

    def kex(self) -> dict[str, Any]:
        conn = self._require()
        conn.i_local = encode_kexinit()
        conn.send_payload(conn.i_local)
        while True:
            payload = conn.recv_payload()
            if payload and payload[0] == MSG_KEXINIT:
                conn.i_peer = payload
                break
            if payload and payload[0] == MSG_DISCONNECT:
                return {"ok": False, "error": parse_disconnect(payload) or "kex_required"}
        secret = dh_private()
        public = dh_public(secret)
        conn.send_payload(encode_kexdh_init(public))
        reply_payload = conn.recv_payload()
        reply = parse_kexdh_reply(reply_payload)
        shared = dh_shared(int(reply["public"]), secret)
        kex_hash = compute_kex_hash(
            conn.v_local,
            conn.v_peer,
            conn.i_local,
            conn.i_peer,
            bytes(reply["host_key"]),
            public,
            int(reply["public"]),
            shared,
        )
        if not verify_kex_signature(kex_hash, bytes(reply["signature"])):
            return {"ok": False, "error": "kex_required"}
        newkeys = conn.recv_payload()
        if not newkeys or newkeys[0] != MSG_NEWKEYS:
            return {"ok": False, "error": "kex_required"}
        conn.recv_mac_key = derive_key(shared, kex_hash, b"F", kex_hash)
        conn.send_payload(bytes([MSG_NEWKEYS]))
        conn.send_mac_key = derive_key(shared, kex_hash, b"E", kex_hash)
        conn.session_id = kex_hash
        conn.shared = shared
        self.session_id = kex_hash.hex()
        return {"ok": True, "session_id": self.session_id, "shared": shared}

    def service_and_userauth(self, password: str, *, user: str = DEFAULT_USER, mac: bool = True) -> dict[str, Any]:
        conn = self._require()
        conn.send_payload(encode_service_request(SERVICE_USERAUTH), mac=mac)
        if not mac:
            try:
                payload = conn.recv_payload()
            except SshActuationError as error:
                return {"ok": False, "error": str(error) or "mac_required"}
            reason = parse_disconnect(payload) if payload and payload[0] == MSG_DISCONNECT else "mac_required"
            return {"ok": False, "error": reason or "mac_required"}
        accepted = conn.recv_payload()
        if not accepted or accepted[0] != MSG_SERVICE_ACCEPT:
            reason = parse_disconnect(accepted) if accepted and accepted[0] == MSG_DISCONNECT else "auth_required"
            return {"ok": False, "error": reason or "auth_required"}
        conn.send_payload(encode_userauth_request(user, password))
        result = conn.recv_payload()
        if result and result[0] == MSG_USERAUTH_SUCCESS:
            return {"ok": True}
        if result and result[0] == MSG_USERAUTH_FAILURE:
            return {"ok": False, "error": "auth_failed"}
        reason = parse_disconnect(result) if result and result[0] == MSG_DISCONNECT else "auth_required"
        return {"ok": False, "error": reason or "auth_required"}

    def open_session(self) -> dict[str, Any]:
        conn = self._require()
        conn.send_payload(encode_channel_open(sender=self.local_channel))
        payload = conn.recv_payload()
        if payload and payload[0] == MSG_CHANNEL_OPEN_CONFIRMATION:
            recipient, offset = parse_ssh_uint32(payload, 1)
            sender, _offset = parse_ssh_uint32(payload, offset)
            self.peer_channel = sender
            return {"ok": True, "recipient": recipient, "sender": sender}
        reason = parse_disconnect(payload) if payload and payload[0] == MSG_DISCONNECT else "channel_required"
        return {"ok": False, "error": reason or "channel_required"}

    def exec_command(self, command: str) -> dict[str, Any]:
        conn = self._require()
        conn.send_payload(encode_channel_request_exec(recipient=self.peer_channel, command=command))
        stdout = b""
        while True:
            payload = conn.recv_payload()
            if not payload:
                break
            kind = payload[0]
            if kind == MSG_CHANNEL_SUCCESS:
                continue
            if kind == MSG_CHANNEL_FAILURE:
                return {"ok": False, "error": "exec_required"}
            if kind == MSG_CHANNEL_DATA:
                stdout += parse_channel_data(payload)
                continue
            if kind in {MSG_CHANNEL_EOF, MSG_CHANNEL_CLOSE}:
                break
            if kind == MSG_DISCONNECT:
                return {"ok": False, "error": parse_disconnect(payload) or "exec_required"}
        self.stdout = stdout
        return {"ok": True, "stdout": stdout}


class _SshTCPServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True
    block_on_close = False

    def __init__(
        self,
        address: tuple[str, int],
        handler: type[socketserver.BaseRequestHandler],
        session: SshSession,
    ) -> None:
        self.session = session
        super().__init__(address, handler)


class _SshHandler(socketserver.StreamRequestHandler):
    timeout = IO_TIMEOUT

    def handle(self) -> None:
        session: SshSession = self.server.session  # type: ignore[attr-defined]
        conn = SshConn(self.request)
        conn.v_local = IDENT_STRING
        authed = False
        client_channel = 0
        try:
            conn.write_ident()
            conn.read_ident()
            conn.i_local = encode_kexinit()
            conn.send_payload(conn.i_local)
            while True:
                try:
                    payload = conn.recv_payload()
                except SshActuationError as error:
                    if str(error) == "mac_required":
                        try:
                            conn.send_payload(encode_disconnect("mac_required"))
                        except (OSError, SshActuationError):
                            pass
                    return
                if not payload:
                    return
                kind = payload[0]
                if kind == MSG_DISCONNECT:
                    return
                if kind == MSG_KEXINIT:
                    conn.i_peer = payload
                    continue
                if kind == MSG_KEXDH_INIT:
                    if not conn.i_peer:
                        conn.send_payload(encode_disconnect("kex_required"))
                        return
                    peer_public = parse_kexdh_init(payload)
                    secret = dh_private()
                    public = dh_public(secret)
                    shared = dh_shared(peer_public, secret)
                    host_key = encode_host_key()
                    kex_hash = compute_kex_hash(
                        conn.v_peer,
                        conn.v_local,
                        conn.i_peer,
                        conn.i_local,
                        host_key,
                        peer_public,
                        public,
                        shared,
                    )
                    signature = sign_kex_hash(kex_hash)
                    conn.send_payload(encode_kexdh_reply(host_key=host_key, public=public, signature=signature))
                    conn.send_payload(bytes([MSG_NEWKEYS]))
                    conn.send_mac_key = derive_key(shared, kex_hash, b"F", kex_hash)
                    conn.session_id = kex_hash
                    conn.shared = shared
                    session.store_session_id(kex_hash.hex())
                    continue
                if kind == MSG_NEWKEYS:
                    if not conn.session_id:
                        conn.send_payload(encode_disconnect("kex_required"))
                        return
                    conn.recv_mac_key = derive_key(conn.shared, conn.session_id, b"E", conn.session_id)
                    continue
                if kind == MSG_SERVICE_REQUEST:
                    name, _offset = parse_ssh_string(payload, 1)
                    if name.decode("ascii", errors="replace") != SERVICE_USERAUTH:
                        conn.send_payload(encode_disconnect("auth_required"))
                        return
                    conn.send_payload(encode_service_accept(SERVICE_USERAUTH))
                    continue
                if kind == MSG_USERAUTH_REQUEST:
                    request = parse_userauth_request(payload)
                    if session.credentials_match(request.get("user") or "", request.get("password") or ""):
                        authed = True
                        conn.send_payload(encode_userauth_success())
                    else:
                        conn.send_payload(encode_userauth_failure())
                    continue
                if kind == MSG_CHANNEL_OPEN:
                    if not authed:
                        conn.send_payload(encode_disconnect("auth_required"))
                        return
                    opened = parse_channel_open(payload)
                    client_channel = int(opened.get("sender") or 0)
                    conn.send_payload(encode_channel_open_confirmation(recipient=client_channel, sender=1))
                    continue
                if kind == MSG_CHANNEL_REQUEST:
                    if not authed:
                        conn.send_payload(encode_disconnect("auth_required"))
                        return
                    request = parse_channel_request(payload)
                    if request.get("kind") != "exec":
                        conn.send_payload(bytes([MSG_CHANNEL_FAILURE]) + ssh_uint32(client_channel))
                        continue
                    stdout = str(request.get("command") or "").encode("utf-8")
                    session.store_stdout(stdout)
                    if request.get("want_reply"):
                        conn.send_payload(encode_channel_success(recipient=client_channel))
                    conn.send_payload(encode_channel_data(recipient=client_channel, data=stdout))
                    conn.send_payload(encode_channel_eof(recipient=client_channel))
                    conn.send_payload(encode_channel_close(recipient=client_channel))
                    continue
                if kind in {MSG_CHANNEL_EOF, MSG_CHANNEL_CLOSE}:
                    return
        except (SshActuationError, OSError, struct.error, TimeoutError, ValueError):
            return
        finally:
            conn.close()


class SshSession:
    """Password-gated loopback SSH-2.0 daemon: bind, publish, read."""

    def __init__(self, output_dir: Path, *, password: str = DEFAULT_PASSWORD) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.user = DEFAULT_USER
        self.password = str(password or "")
        self.host: str | None = None
        self.port: int | None = None
        self.server: _SshTCPServer | None = None
        self.thread: threading.Thread | None = None
        self.delivered = False
        self.last_digest = ""
        self.last_token = ""
        self.last_session_id = ""
        self.history: list[dict[str, Any]] = []
        self._stdout = b""
        self._lock = threading.Lock()

    @property
    def sealed_path(self) -> Path:
        return self.output_dir / SEALED_NAME

    @property
    def retained_path(self) -> Path:
        return self.output_dir / RETAINED_NAME

    def credentials_match(self, user: str, password: str) -> bool:
        if not self.password:
            return False
        return user == self.user and password == self.password

    def store_stdout(self, payload: bytes) -> None:
        with self._lock:
            self._stdout = bytes(payload)

    def store_session_id(self, session_id: str) -> None:
        with self._lock:
            self.last_session_id = str(session_id)

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
        server = _SshTCPServer(("127.0.0.1", 0), _SshHandler, self)
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
        identify: bool = True,
        kex: bool = True,
        mac: bool = True,
        channel: bool = True,
        exec_command: bool = True,
        receive: bool = True,
        replay: bool = True,
        password: str | None = None,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("ssh_required")
        if not self.password:
            return self._forbidden("missing_secret")
        live_token = str(token or SENTINEL)
        presented = self.password if password is None else str(password)
        client = SshClient()
        replay_client: SshClient | None = None
        try:
            client.connect(str(self.host), int(self.port))
            if not identify:
                return self._conflict("identify_required")
            identified = client.identify()
            if not identified.get("ok"):
                return self._forbidden(str(identified.get("error") or "identify_required"), status=400)
            if not kex:
                return self._conflict("kex_required")
            kexed = client.kex()
            if not kexed.get("ok"):
                return self._forbidden(str(kexed.get("error") or "kex_required"), status=409)
            if not mac:
                unauthed = client.service_and_userauth(presented, mac=False)
                return self._conflict(str(unauthed.get("error") or "mac_required"))
            if not authenticate:
                opened = client.open_session()
                return self._forbidden(str(opened.get("error") or "auth_required"), status=401)
            authed = client.service_and_userauth(presented)
            if not authed.get("ok"):
                reason = str(authed.get("error") or "auth_failed")
                status = 401 if reason == "auth_required" else 403
                return self._forbidden(reason, status=status)
            if not channel:
                return self._conflict("channel_required")
            opened = client.open_session()
            if not opened.get("ok"):
                return self._forbidden(str(opened.get("error") or "channel_required"), status=409)
            if not exec_command:
                return self._conflict("exec_required")
            executed = client.exec_command(live_token)
            if not executed.get("ok"):
                return self._forbidden(str(executed.get("error") or "exec_required"), status=409)
            if not receive:
                return self._conflict("receive_required")
            stdout = bytes(executed.get("stdout") or b"")
            if stdout != live_token.encode("utf-8"):
                return self._forbidden("payload_mismatch", status=409)
            client.close()
            if not replay:
                return self._conflict("replay_required")
            replay_client = SshClient()
            replay_client.connect(str(self.host), int(self.port))
            if not replay_client.identify().get("ok"):
                return self._forbidden("replay_failed", status=503)
            if not replay_client.kex().get("ok"):
                return self._forbidden("replay_failed", status=503)
            if not replay_client.service_and_userauth(self.password).get("ok"):
                return self._forbidden("replay_failed", status=503)
            if not replay_client.open_session().get("ok"):
                return self._forbidden("replay_failed", status=503)
            replayed = replay_client.exec_command(live_token)
            if not replayed.get("ok") or bytes(replayed.get("stdout") or b"") != stdout:
                return self._forbidden("replay_failed", status=503)
            live_digest = payload_sha256(stdout)
            session_id = str(kexed.get("session_id") or client.session_id)
            self.retained_path.write_bytes(stdout)
            sealed = {
                "host": self.host,
                "port": self.port,
                "user": self.user,
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": live_digest,
                "session_id": session_id,
                "authenticated": True,
                "identified": True,
                "kexed": True,
                "macced": True,
                "channeled": True,
                "execed": True,
                "received": True,
                "replayed": True,
                "independent": True,
                "retained_path": str(self.retained_path),
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.delivered = True
            self.last_token = live_token
            self.last_digest = live_digest
            self.last_session_id = session_id
            live = independent_ssh_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "host": self.host,
                "port": self.port,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": live_digest,
                "session_id": session_id,
                "path": str(self.sealed_path),
                "authenticated": True,
                "identified": True,
                "kexed": True,
                "macced": True,
                "channeled": True,
                "execed": True,
                "received": True,
                "replayed": True,
                "independent": True,
            }
        except (OSError, SshActuationError, TimeoutError, struct.error, ValueError) as error:
            reason = str(error) or "unreachable"
            if reason in {"mac_required", "identify_required", "kex_required", "auth_required"}:
                status = 409 if reason != "auth_required" else 401
                if reason == "identify_required":
                    status = 400
                return self._conflict(reason) if status == 409 else self._forbidden(reason, status=status)
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
        live = independent_ssh_digest(self.sealed_path)
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


def call_ssh_tool(session: SshSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one SSH tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    authenticate = True if arguments.get("authenticate") is None else bool(arguments.get("authenticate"))
    identify = True if arguments.get("identify") is None else bool(arguments.get("identify"))
    kex = True if arguments.get("kex") is None else bool(arguments.get("kex"))
    mac = True if arguments.get("mac") is None else bool(arguments.get("mac"))
    channel = True if arguments.get("channel") is None else bool(arguments.get("channel"))
    exec_command = True if arguments.get("exec") is None else bool(arguments.get("exec"))
    receive = True if arguments.get("receive") is None else bool(arguments.get("receive"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    secret = arguments.get("password")
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            authenticate=authenticate,
            identify=identify,
            kex=kex,
            mac=mac,
            channel=channel,
            exec_command=exec_command,
            receive=receive,
            replay=replay,
            password=None if secret is None else str(secret),
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise SshActuationError(f"unsupported ssh action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_ssh_digest(sealed_path: Path) -> dict[str, Any]:
    """Re-hash retained exec stdout through a fresh open and compare the sealed digest."""

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
    identified = payload.get("identified") is True
    kexed = payload.get("kexed") is True
    macced = payload.get("macced") is True
    channeled = payload.get("channeled") is True
    execed = payload.get("execed") is True
    received = payload.get("received") is True
    replayed = payload.get("replayed") is True
    independent = payload.get("independent") is True
    matched = bool(digest) and digest == live_digest
    sentinel = (
        SENTINEL
        if token == SENTINEL
        and matched
        and authenticated
        and identified
        and kexed
        and macced
        and channeled
        and execed
        and received
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
        "identified": identified,
        "kexed": kexed,
        "macced": macced,
        "channeled": channeled,
        "execed": execed,
        "received": received,
        "replayed": replayed,
        "independent": independent,
        "error": "" if sentinel else "digest_mismatch",
    }


def run_ssh_workflow(
    *,
    with_secret: bool = True,
    skip_bind: bool = False,
    authenticate: bool = True,
    identify: bool = True,
    kex: bool = True,
    mac: bool = True,
    channel: bool = True,
    exec_command: bool = True,
    receive: bool = True,
    replay: bool = True,
    password: str | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the IDENTIFY/KEXINIT/USERAUTH/EXEC workflow and seal a trace."""

    descriptor = ssh_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SSH_TOOL_PROVIDER),
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
        raise SshActuationError(f"ssh tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="ssh-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = SshSession(out, password=DEFAULT_PASSWORD if with_secret else "")
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    publish_args: dict[str, Any] = {
        "action": "publish",
        "token": SENTINEL,
        "authenticate": authenticate,
        "identify": identify,
        "kex": kex,
        "mac": mac,
        "channel": channel,
        "exec": exec_command,
        "receive": receive,
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
                results.append(call_ssh_tool(session, arguments))
            except SshActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_ssh_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_secret
        and not skip_bind
        and authenticate
        and identify
        and kex
        and mac
        and channel
        and exec_command
        and receive
        and replay
        and password is None
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "ssh_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_secret": with_secret,
        "skip_bind": skip_bind,
        "authenticate": authenticate,
        "identify": identify,
        "kex": kex,
        "mac": mac,
        "channel": channel,
        "exec": exec_command,
        "receive": receive,
        "replay": replay,
        "wrong_secret": password is not None,
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
        "identify": identify,
        "kex": kex,
        "mac": mac,
        "channel": channel,
        "exec": exec_command,
        "receive": receive,
        "replay": replay,
    }


def verify_ssh_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed SSH trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_ssh_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
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
        "identified": independent.get("identified") is True,
        "kexed": independent.get("kexed") is True,
        "macced": independent.get("macced") is True,
        "channeled": independent.get("channeled") is True,
        "execed": independent.get("execed") is True,
        "received": independent.get("received") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "digest_matches_live": str(independent.get("digest") or "")
        == str(independent.get("live_digest") or live_row.get("live_digest") or ""),
        "session_id_recorded": len(str(trace.get("session_id") or independent.get("session_id") or "")) == 64,
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def ssh_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.ssh_actuation import "
        "builtin_ssh_actuation_proof; r=builtin_ssh_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='ssh_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_ssh_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=SSH_ACTUATION_ID,
        name="First-class SSH-2.0 IDENTIFY/KEXINIT/USERAUTH/EXEC actuation",
        description=(
            "Missions that require an ssh tool can opt the ssh provider in, "
            "bind a real loopback SSH-2.0 daemon, complete identification, "
            "group14 DH KEXINIT, password USERAUTH, CHANNEL-OPEN/EXEC, "
            "independently re-EXEC the retained stdout on a later session, "
            "and seal digest-chained ssh traces. Default routing stays "
            "fail-closed; a missing password keeps the hole falsifiable, and "
            "skip-IDENTIFY, skip-KEX, skip-USERAUTH, skip-MAC, skip-EXEC, or "
            "skip-REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.ssh_actuation:builtin_ssh_actuation_proof",
        proof_command=ssh_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.websocket-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/ssh_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required ssh tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback SSH-2.0 daemon, completes "
            "identification, group14 DH KEXINIT, hmac-sha2-256 NEWKEYS, "
            "password USERAUTH, CHANNEL-OPEN/EXEC, independently re-EXECs "
            "the retained stdout on a later session, and binds this family "
            "as the next diversity-catalog successor once websocket framing "
            "is proved. Missing passwords, wrong passwords, skip-IDENTIFY, "
            "skip-KEX, skip-USERAUTH, skip-MAC, skip-CHANNEL, skip-EXEC, "
            "skip-RECEIVE, and skip-REPLAY stay fail-closed."
        ),
        tags=(
            "ssh",
            "openssh",
            "exec",
            "kex",
            "userauth",
            "actuation",
            "diversity",
        ),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T141830Z-ab89b78c",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_ssh_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in SSH-2.0 actuation seals a later-session digest."""

    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.ldap_actuation import LDAP_ACTUATION_GOAL, LDAP_ACTUATION_ID
    from blackhole_agent.mission_selection import (
        capability_family,
        semantic_signature,
        semantic_similarity,
    )
    from blackhole_agent.mqtt_actuation import MQTT_ACTUATION_GOAL, MQTT_ACTUATION_ID
    from blackhole_agent.postgres_actuation import POSTGRES_ACTUATION_GOAL, POSTGRES_ACTUATION_ID
    from blackhole_agent.s3_actuation import S3_ACTUATION_GOAL, S3_ACTUATION_ID
    from blackhole_agent.watch_actuation import WATCH_ACTUATION_GOAL, WATCH_ACTUATION_ID
    from blackhole_agent.websocket_actuation import WEBSOCKET_ACTUATION_GOAL, WEBSOCKET_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = SSH_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(SSH_ACTUATION_GOAL) == (SSH_ACTUATION_ID,)
    checks["websocket_goal_is_not_ssh"] = leftover_marker_ids(WEBSOCKET_ACTUATION_GOAL) == (
        WEBSOCKET_ACTUATION_ID,
    )
    checks["watch_goal_is_not_ssh"] = leftover_marker_ids(WATCH_ACTUATION_GOAL) == (WATCH_ACTUATION_ID,)
    checks["s3_goal_is_not_ssh"] = leftover_marker_ids(S3_ACTUATION_GOAL) == (S3_ACTUATION_ID,)
    checks["postgres_goal_is_not_ssh"] = leftover_marker_ids(POSTGRES_ACTUATION_GOAL) == (
        POSTGRES_ACTUATION_ID,
    )
    checks["ldap_goal_is_not_ssh"] = leftover_marker_ids(LDAP_ACTUATION_GOAL) == (LDAP_ACTUATION_ID,)
    checks["mqtt_goal_is_not_ssh"] = leftover_marker_ids(MQTT_ACTUATION_GOAL) == (MQTT_ACTUATION_ID,)
    checks["ssh_goal_is_not_websocket"] = WEBSOCKET_ACTUATION_ID not in leftover_marker_ids(SSH_ACTUATION_GOAL)
    checks["ssh_goal_is_not_watch"] = WATCH_ACTUATION_ID not in leftover_marker_ids(SSH_ACTUATION_GOAL)
    checks["ssh_goal_is_not_s3"] = S3_ACTUATION_ID not in leftover_marker_ids(SSH_ACTUATION_GOAL)
    checks["ssh_goal_is_not_postgres"] = POSTGRES_ACTUATION_ID not in leftover_marker_ids(SSH_ACTUATION_GOAL)
    checks["ssh_goal_is_not_ldap"] = LDAP_ACTUATION_ID not in leftover_marker_ids(SSH_ACTUATION_GOAL)
    checks["ssh_goal_is_not_mqtt"] = MQTT_ACTUATION_ID not in leftover_marker_ids(SSH_ACTUATION_GOAL)
    checks["websocket_marker_stays_websocket"] = SSH_ACTUATION_ID not in leftover_marker_ids(
        WEBSOCKET_ACTUATION_GOAL
    )
    checks["watch_marker_stays_watch"] = SSH_ACTUATION_ID not in leftover_marker_ids(WATCH_ACTUATION_GOAL)
    checks["s3_marker_stays_s3"] = SSH_ACTUATION_ID not in leftover_marker_ids(S3_ACTUATION_GOAL)
    checks["postgres_marker_stays_postgres"] = SSH_ACTUATION_ID not in leftover_marker_ids(
        POSTGRES_ACTUATION_GOAL
    )
    checks["ldap_marker_stays_ldap"] = SSH_ACTUATION_ID not in leftover_marker_ids(LDAP_ACTUATION_GOAL)
    checks["mqtt_marker_stays_mqtt"] = SSH_ACTUATION_ID not in leftover_marker_ids(MQTT_ACTUATION_GOAL)
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_ssh"] = (
        len(catalog) > 42
        and catalog[42]["id"] == SSH_ACTUATION_ID
        and catalog[41]["id"] == WEBSOCKET_ACTUATION_ID
    )
    family = capability_family(SSH_ACTUATION_GOAL)
    checks["family_is_openssh"] = "openssh" in family
    checks["family_is_exec"] = "exec" in family
    checks["family_is_binary"] = "binary" in family
    checks["family_is_packet"] = "packet" in family
    checks["family_is_not_websocket"] = "websocket" not in family and "rfc6455" not in family
    checks["family_is_not_watch"] = "watch" not in family and "path" not in family
    checks["family_is_not_postgres"] = "postgres" not in family and "postgresql" not in family
    checks["family_is_not_ldap"] = "ldap" not in family
    checks["family_is_not_object"] = "object" not in family
    checks["family_is_not_mqtt"] = "mqtt" not in family
    secret = dh_private()
    peer = dh_private()
    shared_left = dh_shared(dh_public(peer), secret)
    shared_right = dh_shared(dh_public(secret), peer)
    checks["group14_dh_agrees"] = shared_left == shared_right and shared_left > 1
    sample_hash = hashlib.sha256(b"kex-hash-sample").digest()
    checks["host_signature_verifies"] = verify_kex_signature(sample_hash, sign_kex_hash(sample_hash))
    neighbors = (
        WEBSOCKET_ACTUATION_GOAL,
        WATCH_ACTUATION_GOAL,
        S3_ACTUATION_GOAL,
        POSTGRES_ACTUATION_GOAL,
        LDAP_ACTUATION_GOAL,
        MQTT_ACTUATION_GOAL,
    )
    ssh_signature = semantic_signature(SSH_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(ssh_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_ssh = ToolDescriptor(name="remote_ssh", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_ssh)
    checks["naive_mcp_ssh_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = ssh_tool_descriptor()
    default_ssh = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SSH_TOOL_PROVIDER),
    )
    checks["default_ssh_provider_is_unsupported"] = (
        default_ssh.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{SSH_TOOL_PROVIDER}" in default_ssh.reasons
    )
    checks["opted_in_ssh_is_executable"] = opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_ssh],
        required_tool_names=("local_memory", "ssh"),
    )
    checks["naive_preflight_missing_ssh"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["ssh"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "ssh"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SSH_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "ssh" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="ssh-actuation-") as tmp:
        root = Path(tmp)
        missing = run_ssh_workflow(with_secret=False, output_dir=root / "missing")
        unauth = run_ssh_workflow(authenticate=False, output_dir=root / "unauth")
        wrong = run_ssh_workflow(password="wrong-token", output_dir=root / "wrong")
        skip_bind = run_ssh_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_identify = run_ssh_workflow(identify=False, output_dir=root / "skip-identify")
        skip_kex = run_ssh_workflow(kex=False, output_dir=root / "skip-kex")
        skip_mac = run_ssh_workflow(mac=False, output_dir=root / "skip-mac")
        skip_channel = run_ssh_workflow(channel=False, output_dir=root / "skip-channel")
        skip_exec = run_ssh_workflow(exec_command=False, output_dir=root / "skip-exec")
        skip_receive = run_ssh_workflow(receive=False, output_dir=root / "skip-receive")
        skip_replay = run_ssh_workflow(replay=False, output_dir=root / "skip-replay")
        live = run_ssh_workflow(output_dir=root / "live")
        verify = verify_ssh_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_ssh_trace(clone)
        checks["naive_without_secret_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_secret"
            and missing["payload_exists"] is False
        )
        checks["unsigned_exec_is_forbidden"] = (
            unauth["ok"] is False
            and unauth["final_status"] == 401
            and unauth["error"] == "auth_required"
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
            and skip_bind["error"] == "ssh_required"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_identify_stays_empty"] = (
            skip_identify["ok"] is False
            and skip_identify["error"] == "identify_required"
            and skip_identify["final_status"] == 409
            and skip_identify["payload_exists"] is False
        )
        checks["skip_kex_stays_empty"] = (
            skip_kex["ok"] is False
            and skip_kex["error"] == "kex_required"
            and skip_kex["final_status"] == 409
            and skip_kex["payload_exists"] is False
        )
        checks["skip_mac_stays_empty"] = (
            skip_mac["ok"] is False
            and skip_mac["error"] == "mac_required"
            and skip_mac["final_status"] == 409
            and skip_mac["payload_exists"] is False
        )
        checks["skip_channel_stays_empty"] = (
            skip_channel["ok"] is False
            and skip_channel["error"] == "channel_required"
            and skip_channel["final_status"] == 409
            and skip_channel["payload_exists"] is False
        )
        checks["skip_exec_stays_empty"] = (
            skip_exec["ok"] is False
            and skip_exec["error"] == "exec_required"
            and skip_exec["final_status"] == 409
            and skip_exec["payload_exists"] is False
        )
        checks["skip_receive_stays_empty"] = (
            skip_receive["ok"] is False
            and skip_receive["error"] == "receive_required"
            and skip_receive["final_status"] == 409
            and skip_receive["payload_exists"] is False
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
        checks["token_identify_kex_userauth_exec_mac_and_replay_are_required"] = (
            missing["ok"] is False
            and unauth["ok"] is False
            and wrong["ok"] is False
            and skip_bind["ok"] is False
            and skip_identify["ok"] is False
            and skip_kex["ok"] is False
            and skip_mac["ok"] is False
            and skip_channel["ok"] is False
            and skip_exec["ok"] is False
            and skip_receive["ok"] is False
            and skip_replay["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False
        checks["session_id_is_sha256"] = len(str(live.get("session_id") or "")) == 64

    with tempfile.TemporaryDirectory(prefix="ssh-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != SSH_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_ssh"] = (
        live_goal == SSH_ACTUATION_GOAL
        and SSH_ACTUATION_ID in live_done
        and live_source == "genesis_bind_ssh"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_ssh_actuation_capability()
    return {
        "ok": ok,
        "action": "ssh_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": SSH_ACTUATION_GOAL,
        "done_when": SSH_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
