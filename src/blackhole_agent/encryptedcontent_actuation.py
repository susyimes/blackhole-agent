"""Drive a first-class Encrypted Content-Encoding tool through RFC 8188 ENCRYPT/DECRYPT.

Tool routing already fails missions that require ``encryptedcontent``: hosted
encryptedcontent endpoints stay on the unsupported MCP provider, and no first-party
encryptedcontent provider is executable. Unbound therefore cannot speak an ENCRYPT,
lockstep a DECRYPT encid handshake over Encrypted Content-Encoding ENCID,
independently poll the stored ecedigest, or seal an ecedigest
an independent later reader can re-open.

This module closes that hole:

- advertise an ``encryptedcontent`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 8188 daemon
- keep a missing-encid client so the encryptedcontent-encid hole stays falsifiable
- refuse DECRYPT until an ENCRYPT lands with a non-empty encid
- independently poll the stored ecedigest on a later client socket
- persist a sealed ecedigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 8297 Early Hints
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
    ENCRYPTEDCONTENT_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    encryptedcontent_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
ENCRYPTEDCONTENT_ACTUATION_ID = "capability.encryptedcontent-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-ECE-OK"
POLL_TOKEN = "BH-ECE-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_ENCID = 0
EMPTY_ECEDIGEST = 0
ECE_FIRST = 0x41  # RFC 8188 aes128gcm (ASCII 'A')
ENCID_SIZE = 4
ECEDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_DECRYPT = 0x02  # RFC 8188 aes128gcm decrypt record
FRAME_ENCRYPT = 0x01  # RFC 8188 aes128gcm encrypt record
CONTENT_CODING = "aes128gcm"
PAD_LAST = 0x02
PAD_MORE = 0x01
RECORD_SIZE = 4096
RFC_IKM_B64 = "yqdlZ-tYemfogSmv7Ws5PQ"
RFC_SALT_B64 = "I1BsxtFttlv3u_Oo94xnmw"
RFC_CIPHER_B64 = "I1BsxtFttlv3u_Oo94xnmwAAEAAA-NAVub2qFgBEuQKRapoZu-IxkIva3MEB1PD-ly8Thjg"
CEK_INFO = b"Content-Encoding: aes128gcm\x00"
NONCE_INFO = b"Content-Encoding: nonce\x00"
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
ENCRYPTEDCONTENT_LEFTOVER = (
    "Later genesis can take RFC 8188 Encrypted Content-Encoding ENCRYPT/DECRYPT over an "
    "encid-gated ecedigest."
)
ENCRYPTEDCONTENT_ACTUATION_DONE_WHEN = (
    f"capability_exists:{ENCRYPTEDCONTENT_ACTUATION_ID};"
    f"capability_proved:{ENCRYPTEDCONTENT_ACTUATION_ID};"
    "no_skill_route"
)
ENCRYPTEDCONTENT_ACTUATION_GOAL = (
    "Repair rfc8188 encryptedcontent encrypt/decrypt cycle cannot land over http "
    "encryptedcontent encid: hosted encryptedcontent endpoints remain unsupported so an ENCRYPT then "
    "DECRYPT encid handshake cannot land and a sealed ecedigest "
    "cannot be produced. A missing encryptedcontent encid stays forbidden; fail-closed "
    "routing never opts the encryptedcontent provider in. An independent later poll of the "
    "stored ecedigest keeps the hole falsifiable."
)


class EncryptedcontentActuationError(RuntimeError):
    """Raised when the Encrypted Content-Encoding session or loopback daemon fixture misbehaves."""


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



def _gf_mul(left: int, right: int) -> int:
    product = 0
    for _ in range(8):
        if right & 1:
            product ^= left
        hi = left & 0x80
        left = (left << 1) & 0xFF
        if hi:
            left ^= 0x1B
        right >>= 1
    return product


def _gf_inv(value: int) -> int:
    if value == 0:
        return 0
    power = value
    for _ in range(6):
        power = _gf_mul(power, power)
        power = _gf_mul(power, value)
    return _gf_mul(power, power)


def _rotl8(value: int, count: int) -> int:
    count &= 7
    return ((value << count) | (value >> (8 - count))) & 0xFF


def _sbox_byte(value: int) -> int:
    inverse = _gf_inv(value)
    return (
        inverse
        ^ _rotl8(inverse, 1)
        ^ _rotl8(inverse, 2)
        ^ _rotl8(inverse, 3)
        ^ _rotl8(inverse, 4)
        ^ 0x63
    ) & 0xFF


SBOX = bytes(_sbox_byte(index) for index in range(256))
RCON = (0x00, 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36)


def aes128_expand(key: bytes) -> tuple[bytes, ...]:
    raw = bytes(key)
    if len(raw) != 16:
        raise EncryptedcontentActuationError("illegal_aes_key")
    words = [list(raw[index : index + 4]) for index in range(0, 16, 4)]
    for index in range(4, 44):
        temp = words[index - 1][:]
        if index % 4 == 0:
            temp = temp[1:] + temp[:1]
            temp = [SBOX[byte] for byte in temp]
            temp[0] ^= RCON[index // 4]
        words.append([left ^ right for left, right in zip(words[index - 4], temp)])
    rounds = []
    for rnd in range(11):
        block = b"".join(bytes(word) for word in words[4 * rnd : 4 * rnd + 4])
        rounds.append(block)
    return tuple(rounds)


def _xtime(value: int) -> int:
    return ((value << 1) ^ 0x1B) & 0xFF if value & 0x80 else (value << 1) & 0xFF


def _mix_column(col: list[int]) -> list[int]:
    a, b, c, d = col
    return [
        _xtime(a) ^ _xtime(b) ^ b ^ c ^ d,
        a ^ _xtime(b) ^ _xtime(c) ^ c ^ d,
        a ^ b ^ _xtime(c) ^ _xtime(d) ^ d,
        _xtime(a) ^ a ^ b ^ c ^ _xtime(d),
    ]


def aes128_encrypt_block(block: bytes, round_keys: tuple[bytes, ...]) -> bytes:
    state = bytearray(block)
    for index in range(16):
        state[index] ^= round_keys[0][index]
    for rnd in range(1, 10):
        state = bytearray(SBOX[byte] for byte in state)
        state[1], state[5], state[9], state[13] = state[5], state[9], state[13], state[1]
        state[2], state[6], state[10], state[14] = state[10], state[14], state[2], state[6]
        state[3], state[7], state[11], state[15] = state[15], state[3], state[7], state[11]
        for col in range(4):
            mixed = _mix_column([state[4 * col], state[4 * col + 1], state[4 * col + 2], state[4 * col + 3]])
            state[4 * col], state[4 * col + 1], state[4 * col + 2], state[4 * col + 3] = mixed
        for index in range(16):
            state[index] ^= round_keys[rnd][index]
    state = bytearray(SBOX[byte] for byte in state)
    state[1], state[5], state[9], state[13] = state[5], state[9], state[13], state[1]
    state[2], state[6], state[10], state[14] = state[10], state[14], state[2], state[6]
    state[3], state[7], state[11], state[15] = state[15], state[3], state[7], state[11]
    for index in range(16):
        state[index] ^= round_keys[10][index]
    return bytes(state)


def _gf128_mul(left: int, right: int) -> int:
    product = 0
    value = right
    for index in range(128):
        if left & (1 << (127 - index)):
            product ^= value
        lsb = value & 1
        value >>= 1
        if lsb:
            value ^= 0xE1000000000000000000000000000000
    return product


def _ghash(h: bytes, aad: bytes, ciphertext: bytes) -> bytes:
    h_int = int.from_bytes(h, "big")
    acc = 0

    def feed(data: bytes) -> None:
        nonlocal acc
        raw = data + (b"\x00" * ((16 - (len(data) % 16)) % 16))
        for offset in range(0, len(raw), 16):
            block = int.from_bytes(raw[offset : offset + 16], "big")
            acc = _gf128_mul(acc ^ block, h_int)

    feed(aad)
    feed(ciphertext)
    lengths = ((len(aad) * 8) << 64) | (len(ciphertext) * 8)
    acc = _gf128_mul(acc ^ lengths, h_int)
    return acc.to_bytes(16, "big")


def _inc32(block: bytes) -> bytes:
    counter = (int.from_bytes(block[12:], "big") + 1) & 0xFFFFFFFF
    return block[:12] + counter.to_bytes(4, "big")


def gcm_crypt(
    key: bytes,
    nonce: bytes,
    plaintext: bytes,
    aad: bytes = b"",
    *,
    decrypt: bool = False,
) -> tuple[bytes, bytes]:
    if len(nonce) != 12:
        raise EncryptedcontentActuationError("illegal_nonce")
    round_keys = aes128_expand(key)
    h = aes128_encrypt_block(b"\x00" * 16, round_keys)
    j0 = nonce + b"\x00\x00\x00\x01"
    counter = _inc32(j0)
    out = bytearray()
    raw = bytes(plaintext or b"")
    for offset in range(0, len(raw), 16):
        keystream = aes128_encrypt_block(counter, round_keys)
        chunk = raw[offset : offset + 16]
        out.extend(left ^ right for left, right in zip(chunk, keystream[: len(chunk)]))
        counter = _inc32(counter)
    ciphertext = bytes(out)
    hashed = raw if decrypt else ciphertext
    tag = bytes(
        left ^ right
        for left, right in zip(aes128_encrypt_block(j0, round_keys), _ghash(h, aad, hashed))
    )
    return ciphertext, tag


def hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    return hmac.new(bytes(salt or b""), bytes(ikm or b""), hashlib.sha256).digest()


def hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    t = b""
    okm = b""
    counter = 1
    while len(okm) < int(length):
        t = hmac.new(prk, t + bytes(info or b"") + bytes([counter]), hashlib.sha256).digest()
        okm += t
        counter += 1
    return okm[: int(length)]


def derive_cek_nonce(ikm: bytes, salt: bytes, keyid: bytes = b"") -> tuple[bytes, bytes]:
    live_keyid = bytes(keyid or b"")
    prk = hkdf_extract(salt, ikm)
    cek = hkdf_expand(prk, CEK_INFO + live_keyid, 16)
    nonce = hkdf_expand(prk, NONCE_INFO + live_keyid, 12)
    return cek, nonce


def record_nonce(base: bytes, seq: int) -> bytes:
    seq_bytes = int(seq).to_bytes(12, "big")
    return bytes(left ^ right for left, right in zip(base, seq_bytes))


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(bytes(data or b"")).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    raw = str(text or "")
    pad = "=" * ((4 - len(raw) % 4) % 4)
    return base64.urlsafe_b64decode(raw + pad)


def encode_ece_header(salt: bytes, rs: int, keyid: bytes = b"") -> bytes:
    live_salt = bytes(salt or b"")
    live_keyid = bytes(keyid or b"")
    if len(live_salt) != 16 or len(live_keyid) > 255 or int(rs) < 18:
        raise EncryptedcontentActuationError("illegal_ece_header")
    return live_salt + struct.pack("!IB", int(rs) & 0xFFFFFFFF, len(live_keyid)) + live_keyid


def parse_ece_header(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 21:
        raise EncryptedcontentActuationError("short_ece_header")
    salt = raw[:16]
    rs, idlen = struct.unpack("!IB", raw[16:21])
    if 21 + int(idlen) > len(raw):
        raise EncryptedcontentActuationError("short_ece_header")
    keyid = raw[21 : 21 + int(idlen)]
    return {
        "salt": salt,
        "rs": int(rs),
        "idlen": int(idlen),
        "keyid": keyid,
        "header_size": 21 + int(idlen),
        "content_coding": CONTENT_CODING,
    }


def encrypt_aes128gcm(
    plaintext: bytes,
    ikm: bytes,
    salt: bytes,
    keyid: bytes = b"",
    rs: int = RECORD_SIZE,
) -> bytes:
    header = encode_ece_header(salt, rs, keyid)
    cek, nonce = derive_cek_nonce(ikm, salt, keyid)
    padded = bytes(plaintext or b"") + bytes([PAD_LAST])
    ciphertext, tag = gcm_crypt(cek, record_nonce(nonce, 0), padded, b"")
    return header + ciphertext + tag


def decrypt_aes128gcm(message: bytes, ikm: bytes) -> bytes:
    header = parse_ece_header(message)
    body = bytes(message)[int(header["header_size"]) :]
    if len(body) < 17:
        raise EncryptedcontentActuationError("short_ece_record")
    ciphertext, tag = body[:-16], body[-16:]
    cek, nonce = derive_cek_nonce(ikm, header["salt"], header["keyid"])
    padded, got = gcm_crypt(cek, record_nonce(nonce, 0), ciphertext, b"", decrypt=True)
    if got != tag:
        raise EncryptedcontentActuationError("ece_tag_failed")
    cut = padded.rstrip(b"\x00")
    if not cut or cut[-1] != PAD_LAST:
        raise EncryptedcontentActuationError("illegal_padding")
    return cut[:-1]


def canonical_encrypt(identity: str, encid: int) -> str:
    """RFC 8188 aes128gcm coding bound to identity and encid."""

    return f"{CONTENT_CODING}; identity={identity}; encid={int(encid) & 0xFFFFFFFF}"


def canonical_decrypt(identity: str, encid: int, ecedigest: int | None = None) -> str:
    """RFC 8188 decrypt of the stored aes128gcm record."""

    suffix = ""
    if ecedigest is not None:
        suffix = f"; ecedigest={int(ecedigest) & 0xFFFFFFFF}"
    return f"{CONTENT_CODING}; identity={identity}; encid={int(encid) & 0xFFFFFFFF}{suffix}"


def representation_ece(identity: str, encid: int, ecedigest: int) -> str:
    return canonical_decrypt(identity, encid, ecedigest)


def ece_header_matches(left: bytes, right: bytes) -> bool:
    return parse_ece_header(left) == parse_ece_header(right)



def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise EncryptedcontentActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise EncryptedcontentActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise EncryptedcontentActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise EncryptedcontentActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def encrypt_request(identity: str, encid: int, body: bytes = b"") -> bytes:
    """HTTP POST that carries RFC 8188 aes128gcm encrypted content."""

    keyid = f"{int(encid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    payload = bytes(body or b"")
    return (
        f"POST /encryptedcontent/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Enc-Id: {int(encid) & 0xFFFFFFFF}\r\n"
        f"Content-Encoding: {CONTENT_CODING}\r\n"
        "Content-Type: application/octet-stream\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def decrypt_request(identity: str, encid: int, ecedigest: int | None = None, body: bytes = b"") -> bytes:
    """HTTP POST retry that decrypts stored RFC 8188 aes128gcm content."""

    keyid = f"{int(encid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if ecedigest is not None:
        extra = f"Ece-Digest: {int(ecedigest) & 0xFFFFFFFF}\r\n"
    payload = bytes(body or b"")
    return (
        f"POST /encryptedcontent/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Enc-Id: {int(encid) & 0xFFFFFFFF}\r\n"
        "Decrypt: 1\r\n"
        f"Content-Encoding: {CONTENT_CODING}\r\n"
        f"{extra}"
        "Content-Type: application/octet-stream\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    ece_kind = "decrypt" if fields.get("decrypt") == "1" else "encrypt"
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "ece_kind": ece_kind,
        "content_encoding": fields.get("content-encoding", ""),
        "encid": int(fields["enc-id"]) if fields.get("enc-id") else EMPTY_ENCID,
        "ecedigest": int(fields["ece-digest"]) if fields.get("ece-digest") else EMPTY_ECEDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else False,
    }


def encrypt_response(identity: str, encid: int, ecedigest: int, body: bytes = b"") -> bytes:
    """HTTP 201 after RFC 8188 aes128gcm ENCRYPT, carrying the stored ecedigest."""

    payload = bytes(body or canonical_encrypt(identity, encid).encode("ascii"))
    return (
        "HTTP/1.1 201 Created\r\n"
        f"Content-Encoding: {CONTENT_CODING}\r\n"
        f"Enc-Id: {int(encid) & 0xFFFFFFFF}\r\n"
        f"Ece-Digest: {int(ecedigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/octet-stream\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def decrypt_response(identity: str, encid: int, ecedigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 8188 aes128gcm DECRYPT, carrying the stored plaintext."""

    payload = bytes(body or representation_ece(identity, encid, ecedigest).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        "Content-Encoding: identity\r\n"
        f"Enc-Id: {int(encid) & 0xFFFFFFFF}\r\n"
        f"Ece-Digest: {int(ecedigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: text/plain\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise EncryptedcontentActuationError("illegal_content_length") from error
    if start.startswith("HTTP/1.1 201"):
        status = 201
        ece_kind = "encrypt"
    elif start.startswith("HTTP/1.1 200"):
        status = 200
        ece_kind = "decrypt"
    else:
        status = 0
        ece_kind = "encrypt"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "content_encoding": fields.get("content-encoding", ""),
        "ece_kind": ece_kind,
        "encid": int(fields["enc-id"]) if fields.get("enc-id") else EMPTY_ENCID,
        "ecedigest": int(fields["ece-digest"]) if fields.get("ece-digest") else EMPTY_ECEDIGEST,
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
        raise EncryptedcontentActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise EncryptedcontentActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise EncryptedcontentActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise EncryptedcontentActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def request_encid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"encid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_encid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-encid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_ecedigest(encid: int = EMPTY_ENCID, token: str = SENTINEL) -> int:
    material = canonical_encrypt(token or SENTINEL, int(encid) & 0xFFFFFFFF).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_ENCID = request_encid(SENTINEL)
DEFAULT_ECEDIGEST = request_ecedigest(DEFAULT_ENCID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    encid: int,
    ecedigest: int,
    include_encid: bool = True,
) -> bytes:
    live_encid = int(encid) & 0xFFFFFFFF if include_encid else EMPTY_ENCID
    live_digest = int(ecedigest) & 0xFFFFFFFF if include_encid and live_encid else EMPTY_ECEDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    prefix_bytes = struct.pack("!I", live_encid) if live_encid else b""
    header = bytearray()
    header.append(ECE_FIRST)
    header.append(len(prefix_bytes))
    header.extend(prefix_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_encrypt(
    *,
    identity: str,
    encid: int,
    ecedigest: int | None = None,
    include_encid: bool = True,
) -> bytes:
    live_encid = int(encid) & 0xFFFFFFFF if include_encid else EMPTY_ENCID
    live_digest = int(ecedigest) if ecedigest is not None else request_ecedigest(live_encid, identity)
    return encode_packet(
        FRAME_ENCRYPT,
        identity=identity,
        encid=live_encid,
        ecedigest=live_digest,
        include_encid=include_encid,
    )


def encode_decrypt(
    *,
    identity: str,
    encid: int,
    ecedigest: int | None = None,
    include_encid: bool = True,
) -> bytes:
    live_encid = int(encid) & 0xFFFFFFFF if include_encid else EMPTY_ENCID
    live_digest = int(ecedigest) if ecedigest is not None else request_ecedigest(live_encid, identity)
    return encode_packet(
        FRAME_DECRYPT,
        identity=identity,
        encid=live_encid,
        ecedigest=live_digest,
        include_encid=include_encid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise EncryptedcontentActuationError("short_packet")
    first = raw[0]
    if first != ECE_FIRST:
        raise EncryptedcontentActuationError("illegal_header")
    offset = 1
    prefix_len = raw[offset]
    offset += 1
    if offset + prefix_len > len(raw):
        raise EncryptedcontentActuationError("short_packet")
    prefix_bytes = raw[offset : offset + prefix_len]
    offset += prefix_len
    if prefix_len == ENCID_SIZE:
        live_encid = struct.unpack("!I", prefix_bytes)[0]
    elif prefix_len == 0:
        live_encid = EMPTY_ENCID
    else:
        raise EncryptedcontentActuationError("illegal_encid")
    if offset >= len(raw):
        raise EncryptedcontentActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_ENCRYPT, FRAME_DECRYPT}:
        raise EncryptedcontentActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise EncryptedcontentActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise EncryptedcontentActuationError("checksum_failed")
    if len(payload) < 5:
        raise EncryptedcontentActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise EncryptedcontentActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_encid = int(live_encid) != EMPTY_ENCID
    has_ecedigest = has_encid and int(live_digest) != EMPTY_ECEDIGEST
    is_encrypt = frame_type == FRAME_ENCRYPT
    is_decrypt = frame_type == FRAME_DECRYPT
    return {
        "type": int(frame_type),
        "is_encrypt": is_encrypt,
        "is_decrypt": is_decrypt,
        "is_response": is_decrypt,
        "encid": int(live_encid),
        "has_encid": has_encid,
        "ecedigest": int(live_digest),
        "has_ecedigest": has_ecedigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "prefix_len": int(prefix_len),
        "encrypted_content": "RFC8188",
        "ece": canonical_encrypt(identity, live_encid) if has_encid else "",
        "plain": canonical_decrypt(identity, live_encid, live_digest) if has_ecedigest else "",
    }


class EncryptedcontentClient:
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
            raise EncryptedcontentActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_decrypt"] or not packet["is_response"]:
            raise EncryptedcontentActuationError("ecedigest_required")
        if not packet["has_encid"]:
            raise EncryptedcontentActuationError("encid_required")
        if not packet["has_ecedigest"]:
            raise EncryptedcontentActuationError("ecedigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_ecedigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_ecedigest:
            raise EncryptedcontentActuationError("ecedigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "encid": int(reply.get("encid") or EMPTY_ENCID),
            "identity": str(reply.get("identity") or ""),
            "ecedigest": int(reply.get("ecedigest") or EMPTY_ECEDIGEST),
        }

    def hint(
        self,
        identity: str,
        encid: int,
        ecedigest: int = EMPTY_ECEDIGEST,
        *,
        wait_ecedigest: bool = True,
        include_encid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_decrypt(
            identity=identity,
            encid=encid,
            ecedigest=ecedigest or request_ecedigest(encid, identity),
            include_encid=include_encid,
        )
        return self.exchange(packet, wait_ecedigest=wait_ecedigest)


class EncryptedcontentSession:
    """ENCID-gated loopback RFC 8188 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        encid_gate: int = DEFAULT_ENCID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.encid_gate = int(encid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.encid = EMPTY_ENCID
        self.ecedigest = EMPTY_ECEDIGEST
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

    def store_encid_once(self, identity: str, encid: int, ecedigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(encid or EMPTY_ENCID)
            live_digest = int(ecedigest or EMPTY_ECEDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.encid = live
                self.ecedigest = live_digest or request_ecedigest(live, name)
                self.stored = True
            return str(self.identity), int(self.encid), int(self.ecedigest)

    def read_encid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.encid), int(self.ecedigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "encid": EMPTY_ENCID,
            "ecedigest": EMPTY_ECEDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _encid_missing(self) -> bool:
        return not int(self.encid_gate or 0)

    def _reply_hint(self, peer: tuple[str, int], identity: str, encid: int, ecedigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_decrypt(
            identity=identity,
            encid=encid,
            ecedigest=ecedigest,
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
            except EncryptedcontentActuationError:
                continue
            if not packet.get("is_encrypt") and not packet.get("is_decrypt"):
                continue
            if not packet.get("has_encid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_encid, stored_digest = self.store_encid_once(
                identity,
                int(packet.get("encid") or EMPTY_ENCID),
                int(packet.get("ecedigest") or EMPTY_ECEDIGEST),
            )
            if not stored_name or not stored_encid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_encrypt"):
                    self.opened = True
                if packet.get("is_decrypt"):
                    self.handshook = True
                self.retrieved = True
            self._reply_hint(peer, stored_name, stored_encid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._encid_missing():
            return self._forbidden("missing_encid")
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
        do_encrypt: bool = True,
        do_decrypt: bool = True,
        do_ecedigest: bool = True,
        replay: bool = True,
        use_encid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._encid_missing():
            return self._forbidden("missing_encid")
        live_token = str(token or SENTINEL)
        origin_encid = request_encid(live_token)
        origin_digest = request_ecedigest(origin_encid, live_token)
        client: EncryptedcontentClient | None = None
        independent: EncryptedcontentClient | None = None
        try:
            client = EncryptedcontentClient(self.host, int(self.port))
            if not do_encrypt:
                return self._conflict("encrypt_required")
            bind_packet = encode_encrypt(
                identity=live_token,
                encid=origin_encid,
                ecedigest=origin_digest,
                include_encid=use_encid,
            )
            if not use_encid:
                try:
                    client.exchange(bind_packet, wait_ecedigest=True)
                except EncryptedcontentActuationError:
                    return self._conflict("encid_required")
                return self._conflict("encid_required")
            client.send(bind_packet)
            if not do_decrypt:
                return self._conflict("decrypt_required")
            proxy_packet = encode_decrypt(
                identity=live_token,
                encid=origin_encid,
                ecedigest=origin_digest,
                include_encid=True,
            )
            if not do_ecedigest:
                try:
                    client.exchange(proxy_packet, wait_ecedigest=False)
                except EncryptedcontentActuationError as error:
                    if str(error) == "ecedigest_required":
                        return self._conflict("ecedigest_required")
                    return self._conflict("ecedigest_required")
                return self._conflict("ecedigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_ecedigest=True)
            except EncryptedcontentActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("encid_required")
                if reason == "ecedigest_required":
                    return self._conflict("ecedigest_required")
                return self._conflict("encrypt_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("encrypt_required")
            if int(reply.get("encid") or EMPTY_ENCID) != origin_encid:
                return self._conflict("ecedigest_required")
            if int(reply.get("ecedigest") or EMPTY_ECEDIGEST) != origin_digest:
                return self._conflict("ecedigest_required")
            self.retrieved = True
            if replay:
                independent = EncryptedcontentClient(self.host, int(self.port))
                try:
                    poll = independent.hint(
                        POLL_TOKEN,
                        poll_encid(live_token),
                        request_ecedigest(poll_encid(live_token), POLL_TOKEN),
                        wait_ecedigest=True,
                    )
                except EncryptedcontentActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_encid, stored_digest = self.read_encid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_encid != origin_encid
                    or stored_digest != origin_digest
                    or int(poll.get("encid") or EMPTY_ENCID) != origin_encid
                    or int(poll.get("ecedigest") or EMPTY_ECEDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_encid}:{origin_digest}:{live_token}:{canonical_encrypt(live_token, origin_encid)}:{canonical_decrypt(live_token, origin_encid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "encid": origin_encid,
                "ecedigest": origin_digest,
                "encrypt_frame": True,
                "decrypt_frame": True,
                "ecedigest_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "encid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_encryptedcontent_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "encid": origin_encid,
                "ecedigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "encrypt_frame": True,
                "decrypt_frame": True,
                "ecedigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "encid_bound": True,
            }
        except (OSError, EncryptedcontentActuationError) as error:
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
        live = independent_encryptedcontent_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "encid": int(live.get("encid") or EMPTY_ENCID),
            "ecedigest": int(live.get("ecedigest") or EMPTY_ECEDIGEST),
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


def call_encryptedcontent_tool(session: EncryptedcontentSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one Encrypted Content-Encoding tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_encrypt = True if arguments.get("encrypt") is None else bool(arguments.get("encrypt"))
    do_decrypt = True if arguments.get("decrypt") is None else bool(arguments.get("decrypt"))
    do_ecedigest = True if arguments.get("ecedigest") is None else bool(arguments.get("ecedigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_encid = True if arguments.get("use_encid") is None else bool(arguments.get("use_encid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_encrypt=do_encrypt,
            do_decrypt=do_decrypt,
            do_ecedigest=do_ecedigest,
            replay=replay,
            use_encid=use_encid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise EncryptedcontentActuationError(f"unsupported encryptedcontent action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_encryptedcontent_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed Encrypted Content-Encoding ecedigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "encid": EMPTY_ENCID,
        "ecedigest": EMPTY_ECEDIGEST,
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
            "encrypt_frame",
            "decrypt_frame",
            "ecedigest_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "encid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    encid = int(payload.get("encid") or EMPTY_ENCID)
    ecedigest = int(payload.get("ecedigest") or EMPTY_ECEDIGEST)
    dual = port > 0 and bool(encid) and bool(ecedigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "encid": encid,
        "ecedigest": ecedigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "encrypt_frame": payload.get("encrypt_frame") is True,
        "decrypt_frame": payload.get("decrypt_frame") is True,
        "ecedigest_response": payload.get("ecedigest_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "encid_bound": payload.get("encid_bound") is True,
    }


def run_encryptedcontent_workflow(
    *,
    with_encid: bool = True,
    skip_bind: bool = False,
    do_encrypt: bool = True,
    do_decrypt: bool = True,
    do_ecedigest: bool = True,
    replay: bool = True,
    use_encid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 8188 ENCRYPT/DECRYPT encid cycle workflow."""

    descriptor = encryptedcontent_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, ENCRYPTEDCONTENT_TOOL_PROVIDER),
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
        raise EncryptedcontentActuationError(f"encryptedcontent tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="encryptedcontent-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = EncryptedcontentSession(out, encid_gate=DEFAULT_ENCID if with_encid else EMPTY_ENCID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "encrypt": do_encrypt,
            "decrypt": do_decrypt,
            "ecedigest": do_ecedigest,
            "replay": replay,
            "use_encid": use_encid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_encryptedcontent_tool(session, arguments))
            except EncryptedcontentActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_encryptedcontent_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_encid
        and not skip_bind
        and do_encrypt
        and do_decrypt
        and do_ecedigest
        and replay
        and use_encid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "encryptedcontent_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_encid": with_encid,
        "skip_bind": skip_bind,
        "encrypt_frame": do_encrypt,
        "decrypt": do_decrypt,
        "ecedigest": do_ecedigest,
        "replay": replay,
        "use_encid": use_encid,
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
        "encid_value": int(publish_result.get("encid") or independent.get("encid") or EMPTY_ENCID),
        "ecedigest_value": int(publish_result.get("ecedigest") or independent.get("ecedigest") or EMPTY_ECEDIGEST),
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
        "encid": int(trace_body["encid_value"] or EMPTY_ENCID),
        "ecedigest": int(trace_body["ecedigest_value"] or EMPTY_ECEDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_encid": with_encid,
        "skip_bind": skip_bind,
        "encrypt_cycle": do_encrypt,
        "decrypt_cycle": do_decrypt,
        "ecedigest_cycle": do_ecedigest,
        "replay": replay,
        "use_encid": use_encid,
    }


def verify_encryptedcontent_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Encrypted Content-Encoding trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_encryptedcontent_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    encid = int(trace.get("encid_value") or independent.get("encid") or EMPTY_ENCID)
    ecedigest = int(trace.get("ecedigest_value") or independent.get("ecedigest") or EMPTY_ECEDIGEST)
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
        "encrypt_frame": independent.get("encrypt_frame") is True,
        "decrypt_frame": independent.get("decrypt_frame") is True,
        "ecedigest_response": independent.get("ecedigest_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "encid_bound": independent.get("encid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "ecedigest_recorded": (
            port > 0
            and encid == DEFAULT_ENCID
            and ecedigest == DEFAULT_ECEDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def encryptedcontent_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.encryptedcontent_actuation import "
        "builtin_encryptedcontent_actuation_proof; r=builtin_encryptedcontent_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='encryptedcontent_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_encryptedcontent_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=ENCRYPTEDCONTENT_ACTUATION_ID,
        name="First-class RFC 8188 Encrypted Content-Encoding ENCRYPT/DECRYPT actuation",
        description=(
            "Missions that require an encryptedcontent tool can opt the encryptedcontent provider in, "
            "bind a loopback RFC 8188 Encrypted Content-Encoding origin, complete an ENCRYPT "
            "with a non-empty encid, lockstep a DECRYPT that carries the "
            "stored ecedigest, independently poll the stored ecedigest "
            "on a later socket, and seal a digest-chained ecedigest. Default "
            "routing stays fail-closed; a missing encid keeps the hole "
            "falsifiable, and skip-ENCRYPT/DECRYPT/ECEDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.encryptedcontent_actuation:builtin_encryptedcontent_actuation_proof",
        proof_command=encryptedcontent_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.earlyhints-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/encryptedcontent_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/altsvc_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required encryptedcontent tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 8188 daemon, speaks an "
            "ENCRYPT then DECRYPT over Encrypted Content-Encoding with a non-empty encid and "
            "ecedigest, independently polls the stored ecedigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 8297 Early Hints lockstep is proved. "
            "Missing encids, skip-ENCRYPT, skip-DECRYPT, skip-ecedigest, skip-REPLAY, "
            "and an ENCRYPT aimed without an encid stay fail-closed. "
            "Later genesis can take RFC 7838 HTTP Alternative Services ALTSVC/ORIGIN as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("encryptedcontent", "rfc8188", "http", "encid", "ecedigest", "aes128gcm", "encrypt", "decrypt", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260904T050358Z-386aa453",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_encryptedcontent_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 8188 Encrypted Content-Encoding lockstep actuation seals a ecedigest."""

    from blackhole_agent.altsvc_actuation import (
        ALTSVC_ACTUATION_GOAL,
        ALTSVC_ACTUATION_ID,
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

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = ENCRYPTEDCONTENT_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(ENCRYPTEDCONTENT_ACTUATION_GOAL) == (
        ENCRYPTEDCONTENT_ACTUATION_ID,
    )
    checks["leftover_text_binds_encryptedcontent"] = leftover_marker_ids(ENCRYPTEDCONTENT_LEFTOVER) == (
        ENCRYPTEDCONTENT_ACTUATION_ID,
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
        (EARLYHINTS_ACTUATION_GOAL, EARLYHINTS_ACTUATION_ID, "earlyhints"),
        (ALTSVC_ACTUATION_GOAL, ALTSVC_ACTUATION_ID, "altsvc"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_encryptedcontent"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"encryptedcontent_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            ENCRYPTEDCONTENT_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = ENCRYPTEDCONTENT_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    ikm = b64url_decode(RFC_IKM_B64)
    salt = b64url_decode(RFC_SALT_B64)
    walrus = b"I am the walrus"
    cipher = encrypt_aes128gcm(walrus, ikm, salt)
    header = parse_ece_header(cipher)
    rebuilt = encode_ece_header(header["salt"], header["rs"], header["keyid"])
    asked = parse_http_request(encrypt_request(SENTINEL, DEFAULT_ENCID, cipher))
    decrypt_req = parse_http_request(decrypt_request(SENTINEL, DEFAULT_ENCID, DEFAULT_ECEDIGEST, cipher))
    got = parse_http_response(encrypt_response(SENTINEL, DEFAULT_ENCID, DEFAULT_ECEDIGEST, cipher))
    decrypt_reply = parse_http_response(
        decrypt_response(SENTINEL, DEFAULT_ENCID, DEFAULT_ECEDIGEST, walrus)
    )
    checks["encrypt_roundtrip"] = (
        decrypt_aes128gcm(cipher, ikm) == walrus
        and hmac.compare_digest(rebuilt, cipher[: header["header_size"]])
        and header["rs"] == RECORD_SIZE
        and header["idlen"] == 0
        and header["content_coding"] == CONTENT_CODING
        and b64url(cipher) == RFC_CIPHER_B64
        and aes128_encrypt_block(
            bytes.fromhex("00112233445566778899aabbccddeeff"),
            aes128_expand(bytes(range(16))),
        )
        == bytes.fromhex("69c4e0d86a7b0430d8cdb78070b4c55a")
    )
    checks["decrypt_roundtrip"] = (
        decrypt_aes128gcm(b64url_decode(RFC_CIPHER_B64), ikm) == walrus
        and DEFAULT_ECEDIGEST == request_ecedigest(DEFAULT_ENCID, SENTINEL)
        and "ecedigest=" in canonical_decrypt(SENTINEL, DEFAULT_ENCID, DEFAULT_ECEDIGEST)
        and canonical_encrypt(SENTINEL, DEFAULT_ENCID).startswith(CONTENT_CODING)
    )
    checks["encrypt_decrypt_http_roundtrip"] = (
        asked["method"] == "POST"
        and asked["ece_kind"] == "encrypt"
        and asked["content_encoding"] == CONTENT_CODING
        and asked["encid"] == DEFAULT_ENCID
        and decrypt_req["ece_kind"] == "decrypt"
        and decrypt_req["ecedigest"] == DEFAULT_ECEDIGEST
        and decrypt_req["content_encoding"] == CONTENT_CODING
        and got["status"] == 201
        and decrypt_reply["status"] == 200
        and got["content_encoding"] == CONTENT_CODING
        and decrypt_reply["content_encoding"] == "identity"
        and got["content_length_matches_body"] is True
        and decrypt_reply["content_length_matches_body"] is True
        and got["ecedigest"] == DEFAULT_ECEDIGEST
        and decrypt_reply["ecedigest"] == DEFAULT_ECEDIGEST
        and ece_header_matches(got["body"][:21], cipher[:21])
    )
    checks["catalog_names_encryptedcontent"] = (
        len(catalog) > 79
        and catalog[79]["id"] == ENCRYPTEDCONTENT_ACTUATION_ID
        and catalog[78]["id"] == EARLYHINTS_ACTUATION_ID
        and catalog[79]["source"] == "genesis_bind_encryptedcontent"
    )
    checks["catalog_names_altsvc"] = (
        len(catalog) > 80
        and catalog[80]["id"] == ALTSVC_ACTUATION_ID
        and catalog[80]["source"] == "genesis_bind_altsvc"
    )
    family = capability_family(ENCRYPTEDCONTENT_ACTUATION_GOAL)
    checks["family_is_encryptedcontent"] = "encryptedcontent" in family
    checks["family_is_encrypt_surface"] = "encryptedcontent" in family
    checks["family_is_encid"] = "encid" in family
    checks["family_is_rfc8188"] = "rfc8188" in family
    checks["family_is_ecedigest"] = "ecedigest" in family
    checks["family_is_not_altsvc"] = (
        "altsvc" not in family
        and "rfc7838" not in family
        and "altsvcid" not in family
        and "origindigest" not in family
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
    packed = encode_encrypt(identity=SENTINEL, encid=DEFAULT_ENCID, ecedigest=DEFAULT_ECEDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_encrypt"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_encid"] is True
        and parsed["encid"] == DEFAULT_ENCID
        and parsed["ecedigest"] == DEFAULT_ECEDIGEST
        and parsed["is_response"] is False
        and parsed["is_decrypt"] is False
        and parsed["type"] == FRAME_ENCRYPT
        and parsed["first_byte"] == ECE_FIRST
    )
    shook = encode_decrypt(
        identity=SENTINEL,
        encid=DEFAULT_ENCID,
        ecedigest=DEFAULT_ECEDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_decrypt"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_encrypt"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["encid"] == DEFAULT_ENCID
        and answer_parsed["ecedigest"] == DEFAULT_ECEDIGEST
        and answer_parsed["has_ecedigest"] is True
        and answer_parsed["type"] == FRAME_DECRYPT
        and answer_parsed["first_byte"] == ECE_FIRST
    )
    bare = encode_encrypt(identity=SENTINEL, encid=DEFAULT_ENCID, include_encid=False)
    checks["missing_encid_is_unauthenticated"] = parse_message(bare)["has_encid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    encryptedcontent_signature = semantic_signature(ENCRYPTEDCONTENT_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(encryptedcontent_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_encryptedcontent = ToolDescriptor(name="remote_encryptedcontent", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_encryptedcontent)
    checks["naive_mcp_encryptedcontent_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = encryptedcontent_tool_descriptor()
    default_encryptedcontent = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, ENCRYPTEDCONTENT_TOOL_PROVIDER),
    )
    checks["default_encryptedcontent_provider_is_unsupported"] = (
        default_encryptedcontent.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{ENCRYPTEDCONTENT_TOOL_PROVIDER}" in default_encryptedcontent.reasons
    )
    checks["opted_in_encryptedcontent_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_encryptedcontent],
        required_tool_names=("local_memory", "encryptedcontent"),
    )
    checks["naive_preflight_missing_encryptedcontent"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["encryptedcontent"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "encryptedcontent"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, ENCRYPTEDCONTENT_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "encryptedcontent" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="encryptedcontent-actuation-") as tmp:
        root = Path(tmp)
        missing = run_encryptedcontent_workflow(with_encid=False, output_dir=root / "missing")
        skip_bind = run_encryptedcontent_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_encrypt = run_encryptedcontent_workflow(do_encrypt=False, output_dir=root / "skip-encrypt")
        skip_decrypt = run_encryptedcontent_workflow(do_decrypt=False, output_dir=root / "skip-decrypt")
        skip_ecedigest = run_encryptedcontent_workflow(do_ecedigest=False, output_dir=root / "skip-ecedigest")
        skip_replay = run_encryptedcontent_workflow(replay=False, output_dir=root / "skip-replay")
        skip_encid = run_encryptedcontent_workflow(use_encid=False, output_dir=root / "skip-encid")
        live = run_encryptedcontent_workflow(output_dir=root / "live")
        verify = verify_encryptedcontent_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_encryptedcontent_trace(clone)
        checks["naive_without_encid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_encid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_encrypt_stays_empty"] = (
            skip_encrypt["ok"] is False
            and skip_encrypt["error"] == "encrypt_required"
            and skip_encrypt["final_status"] == 409
            and skip_encrypt["payload_exists"] is False
        )
        checks["skip_decrypt_stays_empty"] = (
            skip_decrypt["ok"] is False
            and skip_decrypt["error"] == "decrypt_required"
            and skip_decrypt["final_status"] == 409
            and skip_decrypt["payload_exists"] is False
        )
        checks["skip_ecedigest_stays_empty"] = (
            skip_ecedigest["ok"] is False
            and skip_ecedigest["error"] == "ecedigest_required"
            and skip_ecedigest["final_status"] == 409
            and skip_ecedigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_encid_stays_empty"] = (
            skip_encid["ok"] is False
            and skip_encid["error"] == "encid_required"
            and skip_encid["final_status"] == 409
            and skip_encid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_ecedigest"] = (
            int(live.get("encid") or 0) == DEFAULT_ENCID
            and int(live.get("ecedigest") or 0) == DEFAULT_ECEDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_encid_encode_decrypt_ecedigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_encrypt["ok"] is False
            and skip_decrypt["ok"] is False
            and skip_ecedigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_encid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="encryptedcontent-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != ENCRYPTEDCONTENT_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_encryptedcontent"] = (
        live_goal == ENCRYPTEDCONTENT_ACTUATION_GOAL
        and ENCRYPTEDCONTENT_ACTUATION_ID in live_done
        and live_source == "genesis_bind_encryptedcontent"
    )

    with tempfile.TemporaryDirectory(prefix="encryptedcontent-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(ENCRYPTEDCONTENT_LEFTOVER, root)
        register_catalog_proved(root, ENCRYPTEDCONTENT_ACTUATION_ID)
        reason = leftover_satisfied_by(ENCRYPTEDCONTENT_LEFTOVER, root)
        after = leftover_is_open(ENCRYPTEDCONTENT_LEFTOVER, root)
    checks["encryptedcontent_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_encryptedcontent_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{ENCRYPTEDCONTENT_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_encryptedcontent_actuation_capability()
    return {
        "ok": ok,
        "action": "encryptedcontent_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": ENCRYPTEDCONTENT_ACTUATION_GOAL,
        "done_when": ENCRYPTEDCONTENT_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
