"""Decode RFC 6455 frames. Exit 0 for both a miss and a hit.

The same probe runs against the previous milestone source and the candidate
source. It prints one JSON object with boolean passed and a nonempty observed
object. A missing decoder is an unmet outcome, not a crash.
"""

from __future__ import annotations

import json


# RFC 6455 section 5.7, published vectors.
UNMASKED_HELLO = bytes.fromhex("81 05 48 65 6c 6c 6f")
MASKED_HELLO = bytes.fromhex("81 85 37 fa 21 3d 7f 9f 4d 51 58")
# Unmasked "Hel" / ping / "lo". The ping sits inside the data message.
SPLIT_HELLO = bytes.fromhex("01 03 48 65 6c 89 00 80 02 6c 6f")
# Client mask, 16-bit length 1 for a one-byte payload. Not the short form.
NON_MINIMAL = bytes.fromhex("81 fe 00 01 00 00 00 00 41")
# Masked close, zero key, status 1000.
CLOSE_1000 = bytes.fromhex("88 82 00 00 00 00 03 e8")
# Forbidden on the wire (RFC 6455 section 7.4.1).
CLOSE_1005 = bytes.fromhex("88 82 00 00 00 00 03 ed")
# U+00E9 split across two masked client frames. Each fragment is invalid UTF-8.
SPLIT_ACCENT = bytes.fromhex("01 81 01 02 03 04 c2 80 81 01 02 03 04 a8")


def _accent_expected() -> str:
    first = bytes([0xC3 ^ 0x01])
    second = bytes([0xA9 ^ 0x01])
    assert first == bytes.fromhex("c2")
    assert second == bytes.fromhex("a8")
    return bytes([0xC3, 0xA9]).decode("utf-8")


def observe() -> tuple[bool, dict[str, object]]:
    observed: dict[str, object] = {}
    try:
        from blackhole_agent.websocket_frames import decode_websocket_frames
    except ImportError as exc:
        return False, {"error": f"{type(exc).__name__}: {exc}"}
    try:
        client_hello = decode_websocket_frames(MASKED_HELLO, sender="client")
        bare = decode_websocket_frames(UNMASKED_HELLO, sender="client")
        server_hello = decode_websocket_frames(UNMASKED_HELLO, sender="server")
        server_masked = decode_websocket_frames(MASKED_HELLO, sender="server")
        split = decode_websocket_frames(SPLIT_HELLO, sender="server")
        short = decode_websocket_frames(NON_MINIMAL, sender="client")
        closed = decode_websocket_frames(CLOSE_1000, sender="client")
        forbidden = decode_websocket_frames(CLOSE_1005, sender="client")
        accent = decode_websocket_frames(SPLIT_ACCENT, sender="client")
        trail = decode_websocket_frames(UNMASKED_HELLO + b"\x81", sender="server")
    except Exception as exc:  # noqa: BLE001 - unmet outcome must still print JSON
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    text = ""
    if client_hello.get("messages"):
        text = str(client_hello["messages"][0].get("data"))
    split_text = ""
    ping = False
    if split.get("messages"):
        split_text = str(split["messages"][0].get("data"))
    for control in split.get("controls") or ():
        if control.get("kind") == "ping":
            ping = True
    close_code = None
    if closed.get("controls"):
        close_code = closed["controls"][0].get("code")
    accent_text = ""
    if accent.get("messages"):
        accent_text = str(accent["messages"][0].get("data"))

    observed = {
        "text": text,
        "client_ok": bool(client_hello.get("ok")),
        "mask_error": bare.get("error"),
        "server_text": server_hello["messages"][0].get("data") if server_hello.get("messages") else "",
        "server_mask_error": server_masked.get("error"),
        "split_text": split_text,
        "ping": ping,
        "short_error": short.get("error"),
        "close_code": close_code,
        "forbidden_close": forbidden.get("error"),
        "accent": accent_text,
        "trail_text": trail["messages"][0].get("data") if trail.get("messages") else "",
        "trail_consumed": trail.get("consumed"),
        "trail_remainder": trail.get("remainder"),
    }
    passed = bool(
        observed["client_ok"]
        and observed["text"] == "Hello"
        and observed["mask_error"] == "mask"
        and observed["server_text"] == "Hello"
        and observed["server_mask_error"] == "mask"
        and observed["split_text"] == "Hello"
        and observed["ping"] is True
        and observed["short_error"] == "non-minimal-length"
        and observed["close_code"] == 1000
        and observed["forbidden_close"] == "close"
        and observed["accent"] == _accent_expected()
        and observed["trail_text"] == "Hello"
        and observed["trail_consumed"] == len(UNMASKED_HELLO)
        and observed["trail_remainder"] == "truncated"
    )
    return passed, observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"observed": observed, "passed": passed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
