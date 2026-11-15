"""Read a client HTTP/2 connection.

The preface is the 24-byte PRI marker and must be followed by SETTINGS.
A header block split inside an HPACK instruction is one block, and the
dynamic table entry it inserts is readable from the next stream. A client
SETTINGS_INITIAL_WINDOW_SIZE of zero does not shrink the send window.
Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without this reader is an unmet outcome.
"""

from __future__ import annotations

import json

PREFACE = b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"


def frame(frame_type: int, flags: int, stream: int, payload: bytes = b"") -> bytes:
    return (
        len(payload).to_bytes(3, "big")
        + bytes((frame_type, flags))
        + (stream & 0x7FFFFFFF).to_bytes(4, "big")
        + payload
    )


def settings(*pairs: tuple[int, int]) -> bytes:
    body = b"".join(identifier.to_bytes(2, "big") + value.to_bytes(4, "big") for identifier, value in pairs)
    return frame(0x4, 0, 0, body)


def client(*frames: bytes) -> bytes:
    return PREFACE + b"".join(frames)


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.http2_frames import Http2Error, read_http2_connection
    except Exception as exc:  # noqa: BLE001 - baseline without the module still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    def outcome(payload: bytes) -> object:
        try:
            result = read_http2_connection(payload)
        except Http2Error as exc:
            return {"error": exc.code, "reason": exc.reason}
        return {
            "settings": [[identifier, result["settings"][identifier]] for identifier in sorted(result["settings"])],
            "send_window": result["send_window"],
            "receive_window": result["receive_window"],
            "streams": [
                {
                    "id": stream["id"],
                    "headers": stream["headers"],
                    "data": stream["data"].decode("latin-1"),
                    "trailers": stream["trailers"],
                    "end_stream": stream["end_stream"],
                    "send_window": stream["send_window"],
                    "receive_window": stream["receive_window"],
                }
                for stream in result["streams"]
            ],
        }

    name = b"custom-key"
    split = client(
        settings(),
        frame(0x1, 0, 1, bytes((0x40, len(name)))),
        frame(0x9, 0x4, 1, name + bytes((1, ord("1")))),
        frame(0x1, 0x4, 3, b"\xbe"),
    )
    sized = client(
        settings((0x1, 8192)),
        frame(0x1, 0x4, 1, b"\x3f\xe1\x3f\x82"),
    )
    zero_window = client(
        settings((0x4, 0)),
        frame(0x1, 0x4, 1, b"\x82"),
        frame(0x0, 0x1, 1, b"Z"),
    )
    data = b"\x00" * 16384
    opened = settings() + frame(0x1, 0x4, 1, b"\x82")
    flow = client(opened, frame(0x0, 0, 1, data), frame(0x0, 0, 1, data), frame(0x0, 0, 1, data), frame(0x0, 0, 1, data))
    observed: dict[str, object] = {
        "split": outcome(split),
        "table_limit": outcome(sized),
        "zero_receive_window": outcome(zero_window),
        "missing_preface": outcome(b"GET / HTTP/1.1\r\n\r\n"),
        "stream_zero_data": outcome(client(settings(), frame(0x0, 0, 0))),
        "zero_increment": outcome(client(settings(), frame(0x8, 0, 0, b"\x00\x00\x00\x00"))),
        "settings_ack_payload": outcome(client(settings(), frame(0x4, 0x1, 0, b"\x00\x01\x00\x00\x10\x00"))),
        "oversized": outcome(client(settings(), (16385).to_bytes(3, "big") + bytes((0x0, 0)) + (1).to_bytes(4, "big"))),
        "tiny_max_frame": outcome(client(settings((0x5, 16383)))),
        "pad": outcome(client(settings(), frame(0x1, 0x4, 1, b"\x82"), frame(0x0, 0x8, 1, b"\x01"))),
        "broken_continuation": outcome(client(settings(), frame(0x1, 0, 1, b"\x82"), frame(0x6, 0, 0, b"\x00" * 8))),
        "flow_control": outcome(flow),
        "late_stream": outcome(client(settings(), frame(0x1, 0x4, 3, b"\x82"), frame(0x1, 0x4, 1, b"\x82"))),
        "bare_size_update": outcome(client(settings(), frame(0x1, 0x4, 1, b"\x3f\xe1\x3f\x82"))),
    }
    passed = observed == {
        "split": {
            "settings": [],
            "send_window": 65535,
            "receive_window": 65535,
            "streams": [
                {
                    "id": 1,
                    "headers": [("custom-key", "1")],
                    "data": "",
                    "trailers": [],
                    "end_stream": False,
                    "send_window": 65535,
                    "receive_window": 65535,
                },
                {
                    "id": 3,
                    "headers": [("custom-key", "1")],
                    "data": "",
                    "trailers": [],
                    "end_stream": False,
                    "send_window": 65535,
                    "receive_window": 65535,
                },
            ],
        },
        "table_limit": {
            "settings": [[1, 8192]],
            "send_window": 65535,
            "receive_window": 65535,
            "streams": [
                {
                    "id": 1,
                    "headers": [(":method", "GET")],
                    "data": "",
                    "trailers": [],
                    "end_stream": False,
                    "send_window": 65535,
                    "receive_window": 65535,
                }
            ],
        },
        "zero_receive_window": {
            "settings": [[4, 0]],
            "send_window": 65534,
            "receive_window": 65535,
            "streams": [
                {
                    "id": 1,
                    "headers": [(":method", "GET")],
                    "data": "Z",
                    "trailers": [],
                    "end_stream": True,
                    "send_window": 65534,
                    "receive_window": 0,
                }
            ],
        },
        "missing_preface": {"error": "PROTOCOL_ERROR", "reason": "preface"},
        "stream_zero_data": {"error": "PROTOCOL_ERROR", "reason": "stream-zero"},
        "zero_increment": {"error": "PROTOCOL_ERROR", "reason": "increment"},
        "settings_ack_payload": {"error": "FRAME_SIZE_ERROR", "reason": "settings-ack"},
        "oversized": {"error": "FRAME_SIZE_ERROR", "reason": "frame-size"},
        "tiny_max_frame": {"error": "PROTOCOL_ERROR", "reason": "settings-range"},
        "pad": {"error": "PROTOCOL_ERROR", "reason": "pad"},
        "broken_continuation": {"error": "PROTOCOL_ERROR", "reason": "continuation"},
        "flow_control": {"error": "FLOW_CONTROL_ERROR", "reason": "flow-control"},
        "late_stream": {"error": "PROTOCOL_ERROR", "reason": "stream-id"},
        "bare_size_update": {"error": "COMPRESSION_ERROR", "reason": "compression"},
    }
    return passed, observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
