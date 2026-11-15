"""Read a client HTTP/2 connection preface and the frames that follow it.

HPACK decodes one header block. This reader is the connection around that
block: the 24-byte client preface, the required preface SETTINGS frame,
stream identifiers, CONTINUATION assembly, padding, settings limits, and
flow-control windows from RFC 9113.

The buffer is the client's application data only. The server's WINDOW_UPDATE
and SETTINGS frames are not in it, so the client's send window starts at
the default 65,535 octets and shrinks as DATA frames are read. A
SETTINGS_INITIAL_WINDOW_SIZE from the client changes the client's receive
window, which is how much the server may send, and does not grant the
client more room to send.
"""

from __future__ import annotations

from blackhole_agent.hpack import HpackDecoder, HpackError

PREFACE = b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"
_DEFAULT_WINDOW = 65535
_DEFAULT_MAX_FRAME = 16384
_MAX_WINDOW = 2**31 - 1
_MIN_MAX_FRAME = 16384
_MAX_MAX_FRAME = 2**24 - 1

_DATA = 0x0
_HEADERS = 0x1
_PRIORITY = 0x2
_RST_STREAM = 0x3
_SETTINGS = 0x4
_PUSH_PROMISE = 0x5
_PING = 0x6
_GOAWAY = 0x7
_WINDOW_UPDATE = 0x8
_CONTINUATION = 0x9

_END_STREAM = 0x1
_ACK = 0x1
_END_HEADERS = 0x4
_PADDED = 0x8
_PRIORITY_FLAG = 0x20

_HEADER_TABLE_SIZE = 0x1
_ENABLE_PUSH = 0x2
_INITIAL_WINDOW_SIZE = 0x4
_MAX_FRAME_SIZE = 0x5


class Http2Error(ValueError):
    """The client byte stream is not a valid HTTP/2 connection prefix."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(f"{code}: {reason}")
        self.code = code
        self.reason = reason


def read_http2_connection(payload: bytes) -> dict[str, object]:
    """Parse one client preface and every complete frame after it.

    Returns the peer settings, both flow-control windows, and one record
    per stream opened by HEADERS. Raises ``Http2Error`` for a connection
    error. ``code`` is the RFC 9113 error name.
    """

    return _Reader(payload).read()


class _Reader:
    def __init__(self, payload: bytes) -> None:
        if not isinstance(payload, (bytes, bytearray)):
            raise TypeError("connection must be bytes")
        self._data = bytes(payload)
        self._offset = 0
        self._max_frame = _DEFAULT_MAX_FRAME
        self._initial_window = _DEFAULT_WINDOW
        self._send_window = _DEFAULT_WINDOW
        self._receive_window = _DEFAULT_WINDOW
        self._decoder = HpackDecoder()
        self._settings: dict[int, int] = {}
        self._streams: dict[int, dict[str, object]] = {}
        self._order: list[int] = []
        self._highest_id = 0
        self._preface_settings = False
        self._expect_stream = 0
        self._fragment = bytearray()
        self._fragment_end = False
        self._fragment_trailers = False

    def read(self) -> dict[str, object]:
        if not self._data.startswith(PREFACE):
            self._fail("PROTOCOL_ERROR", "preface")
        self._offset = len(PREFACE)
        while self._offset < len(self._data):
            self._frame()
        if not self._preface_settings or self._expect_stream:
            self._fail("PROTOCOL_ERROR", "truncated")
        return {
            "settings": dict(self._settings),
            "send_window": self._send_window,
            "receive_window": self._receive_window,
            "streams": [self._public(self._streams[stream_id]) for stream_id in self._order],
        }

    def _frame(self) -> None:
        if len(self._data) - self._offset < 9:
            self._fail("PROTOCOL_ERROR", "truncated")
        start = self._offset
        length = int.from_bytes(self._data[start : start + 3], "big")
        frame_type = self._data[start + 3]
        flags = self._data[start + 4]
        stream_id = int.from_bytes(self._data[start + 5 : start + 9], "big") & 0x7FFFFFFF
        if length > self._max_frame:
            self._fail("FRAME_SIZE_ERROR", "frame-size")
        end = start + 9 + length
        if end > len(self._data):
            self._fail("PROTOCOL_ERROR", "truncated")
        payload = self._data[start + 9 : end]
        self._offset = end
        if not self._preface_settings and (frame_type != _SETTINGS or flags & _ACK or stream_id != 0):
            self._fail("PROTOCOL_ERROR", "preface-settings")
        if self._expect_stream and not (frame_type == _CONTINUATION and stream_id == self._expect_stream):
            self._fail("PROTOCOL_ERROR", "continuation")
        if frame_type == _DATA:
            self._data_frame(stream_id, flags, payload)
        elif frame_type == _HEADERS:
            self._headers(stream_id, flags, payload)
        elif frame_type == _PRIORITY:
            self._priority(stream_id, payload)
        elif frame_type == _RST_STREAM:
            self._reset(stream_id, payload)
        elif frame_type == _SETTINGS:
            self._settings_frame(stream_id, flags, payload)
        elif frame_type == _PUSH_PROMISE:
            self._fail("PROTOCOL_ERROR", "push")
        elif frame_type == _PING:
            self._ping(stream_id, payload)
        elif frame_type == _GOAWAY:
            self._goaway(stream_id, payload)
        elif frame_type == _WINDOW_UPDATE:
            self._window_update(stream_id, payload)
        elif frame_type == _CONTINUATION:
            self._continuation(stream_id, flags, payload)
        self._mark_preface(frame_type, flags, stream_id)

    def _mark_preface(self, frame_type: int, flags: int, stream_id: int) -> None:
        if self._preface_settings:
            return
        if frame_type != _SETTINGS or flags & _ACK or stream_id != 0:
            self._fail("PROTOCOL_ERROR", "preface-settings")
        self._preface_settings = True

    def _data_frame(self, stream_id: int, flags: int, payload: bytes) -> None:
        if stream_id == 0:
            self._fail("PROTOCOL_ERROR", "stream-zero")
        data = self._unpad(payload, flags)
        stream = self._open_stream(stream_id)
        if stream["end_stream"]:
            self._fail("STREAM_CLOSED", "stream-closed")
        if len(payload) > self._send_window or len(payload) > int(stream["send_window"]):
            self._fail("FLOW_CONTROL_ERROR", "flow-control")
        self._send_window -= len(payload)
        stream["send_window"] = int(stream["send_window"]) - len(payload)
        stream["data"] = bytes(stream["data"]) + data
        if flags & _END_STREAM:
            stream["end_stream"] = True

    def _headers(self, stream_id: int, flags: int, payload: bytes) -> None:
        if stream_id == 0:
            self._fail("PROTOCOL_ERROR", "stream-zero")
        if stream_id % 2 == 0:
            self._fail("PROTOCOL_ERROR", "even-stream")
        fragment = self._header_fragment(payload, flags)
        trailers = stream_id in self._streams and bool(self._streams[stream_id]["headers_done"])
        if trailers and not flags & _END_STREAM:
            self._fail("PROTOCOL_ERROR", "trailers")
        if flags & _END_HEADERS:
            self._finish_headers(stream_id, fragment, bool(flags & _END_STREAM), trailers)
            return
        self._expect_stream = stream_id
        self._fragment = bytearray(fragment)
        self._fragment_end = bool(flags & _END_STREAM)
        self._fragment_trailers = trailers

    def _continuation(self, stream_id: int, flags: int, payload: bytes) -> None:
        if not self._expect_stream or stream_id != self._expect_stream:
            self._fail("PROTOCOL_ERROR", "continuation")
        self._fragment.extend(payload)
        if not flags & _END_HEADERS:
            return
        fragment = bytes(self._fragment)
        end_stream = self._fragment_end
        trailers = self._fragment_trailers
        self._expect_stream = 0
        self._fragment = bytearray()
        self._finish_headers(stream_id, fragment, end_stream, trailers)

    def _finish_headers(self, stream_id: int, fragment: bytes, end_stream: bool, trailers: bool) -> None:
        try:
            headers = self._decoder.decode(fragment)
        except HpackError:
            self._fail("COMPRESSION_ERROR", "compression")
        if not trailers:
            if stream_id <= self._highest_id:
                self._fail("PROTOCOL_ERROR", "stream-id")
            self._highest_id = stream_id
            stream = {
                "id": stream_id,
                "headers": headers,
                "data": b"",
                "trailers": [],
                "end_stream": end_stream,
                "headers_done": True,
                "send_window": _DEFAULT_WINDOW,
                "receive_window": self._initial_window,
            }
            self._streams[stream_id] = stream
            self._order.append(stream_id)
            return
        stream = self._streams[stream_id]
        if stream["end_stream"]:
            self._fail("STREAM_CLOSED", "stream-closed")
        stream["trailers"] = headers
        stream["end_stream"] = True

    def _priority(self, stream_id: int, payload: bytes) -> None:
        if stream_id == 0:
            self._fail("PROTOCOL_ERROR", "stream-zero")
        if len(payload) != 5:
            self._fail("FRAME_SIZE_ERROR", "frame-size")

    def _reset(self, stream_id: int, payload: bytes) -> None:
        if stream_id == 0:
            self._fail("PROTOCOL_ERROR", "stream-zero")
        if len(payload) != 4:
            self._fail("FRAME_SIZE_ERROR", "frame-size")
        stream = self._open_stream(stream_id)
        stream["end_stream"] = True

    def _settings_frame(self, stream_id: int, flags: int, payload: bytes) -> None:
        if stream_id != 0:
            self._fail("PROTOCOL_ERROR", "stream-zero")
        if flags & _ACK:
            if payload:
                self._fail("FRAME_SIZE_ERROR", "settings-ack")
            return
        if len(payload) % 6 != 0:
            self._fail("FRAME_SIZE_ERROR", "settings-length")
        for index in range(0, len(payload), 6):
            identifier = int.from_bytes(payload[index : index + 2], "big")
            value = int.from_bytes(payload[index + 2 : index + 6], "big")
            self._apply_setting(identifier, value)

    def _apply_setting(self, identifier: int, value: int) -> None:
        if identifier == _HEADER_TABLE_SIZE:
            self._decoder.set_protocol_max(value)
        elif identifier == _ENABLE_PUSH:
            if value not in (0, 1):
                self._fail("PROTOCOL_ERROR", "settings-range")
        elif identifier == _INITIAL_WINDOW_SIZE:
            if value > _MAX_WINDOW:
                self._fail("FLOW_CONTROL_ERROR", "flow-control")
            delta = value - self._initial_window
            self._initial_window = value
            for stream in self._streams.values():
                updated = int(stream["receive_window"]) + delta
                if updated > _MAX_WINDOW:
                    self._fail("FLOW_CONTROL_ERROR", "flow-control")
                stream["receive_window"] = updated
        elif identifier == _MAX_FRAME_SIZE:
            if value < _MIN_MAX_FRAME or value > _MAX_MAX_FRAME:
                self._fail("PROTOCOL_ERROR", "settings-range")
            self._max_frame = value
        elif identifier not in (0x3, 0x6):
            return
        self._settings[identifier] = value

    def _ping(self, stream_id: int, payload: bytes) -> None:
        if stream_id != 0:
            self._fail("PROTOCOL_ERROR", "stream-zero")
        if len(payload) != 8:
            self._fail("FRAME_SIZE_ERROR", "frame-size")

    def _goaway(self, stream_id: int, payload: bytes) -> None:
        if stream_id != 0:
            self._fail("PROTOCOL_ERROR", "stream-zero")
        if len(payload) < 8:
            self._fail("FRAME_SIZE_ERROR", "frame-size")

    def _window_update(self, stream_id: int, payload: bytes) -> None:
        if len(payload) != 4:
            self._fail("FRAME_SIZE_ERROR", "frame-size")
        increment = int.from_bytes(payload, "big") & 0x7FFFFFFF
        if increment == 0:
            self._fail("PROTOCOL_ERROR", "increment")
        if stream_id == 0:
            updated = self._receive_window + increment
            if updated > _MAX_WINDOW:
                self._fail("FLOW_CONTROL_ERROR", "flow-control")
            self._receive_window = updated
            return
        stream = self._open_stream(stream_id)
        updated = int(stream["receive_window"]) + increment
        if updated > _MAX_WINDOW:
            self._fail("FLOW_CONTROL_ERROR", "flow-control")
        stream["receive_window"] = updated

    def _open_stream(self, stream_id: int) -> dict[str, object]:
        stream = self._streams.get(stream_id)
        if stream is None:
            self._fail("PROTOCOL_ERROR", "idle")
        return stream

    def _unpad(self, payload: bytes, flags: int) -> bytes:
        if not flags & _PADDED:
            return payload
        if not payload:
            self._fail("PROTOCOL_ERROR", "pad")
        pad_length = payload[0]
        if pad_length >= len(payload):
            self._fail("PROTOCOL_ERROR", "pad")
        return payload[1 : len(payload) - pad_length]

    def _header_fragment(self, payload: bytes, flags: int) -> bytes:
        body = self._unpad(payload, flags)
        if not flags & _PRIORITY_FLAG:
            return body
        if len(body) < 5:
            self._fail("FRAME_SIZE_ERROR", "frame-size")
        return body[5:]

    def _public(self, stream: dict[str, object]) -> dict[str, object]:
        return {
            "id": stream["id"],
            "headers": list(stream["headers"]),
            "data": bytes(stream["data"]),
            "trailers": list(stream["trailers"]),
            "end_stream": bool(stream["end_stream"]),
            "send_window": int(stream["send_window"]),
            "receive_window": int(stream["receive_window"]),
        }

    def _fail(self, code: str, reason: str) -> None:
        raise Http2Error(code, reason)
