"""Decode WebSocket frames from the bytes on a connection.

RFC 6455 section 5.2 is a length-prefixed binary frame. A client sender
must mask every frame and a server sender must not. A 16-bit length below
126, or a 64-bit length below 65536, is rejected. Control frames may sit
between fragments of one data message. Text is checked as UTF-8 only when
the message is finished, so a code point may cross a frame boundary.

The HTTP upgrade that precedes these frames is a different reader.
"""

from __future__ import annotations

_MAX_MESSAGE = 8 * 1024 * 1024
_FORBIDDEN_CLOSE = frozenset({1004, 1005, 1006, 1015})
_DATA = frozenset({1, 2})
_CONTROL = frozenset({8, 9, 10})


def decode_websocket_frames(data: bytes | bytearray, *, sender: str) -> dict[str, object]:
    """Return the data messages and control frames in ``data``.

    ``sender`` is ``client`` or ``server``, the party that wrote the bytes.
    On success ``ok`` is true and ``consumed`` counts complete frames.
    ``remainder`` is ``truncated`` when the buffer ends inside a later frame
    or an unfinished fragmented message; those bytes stay with the caller.
    A protocol error fails the whole buffer: ``ok`` is false, ``consumed``
    is 0, and both lists are empty.
    """

    if isinstance(data, bytearray):
        view = bytes(data)
    elif isinstance(data, bytes):
        view = data
    else:
        raise TypeError("websocket frames must be bytes")
    if sender not in {"client", "server"}:
        raise ValueError("sender must be client or server")

    messages: list[dict[str, object]] = []
    controls: list[dict[str, object]] = []
    pending: dict[str, object] | None = None
    pending_at = 0
    index = 0
    size = len(view)
    while index < size:
        frame, nxt, problem = _frame(view, index, sender)
        if problem == "truncated":
            cut = pending_at if pending is not None else index
            return _partial(messages, controls, cut, pending)
        if problem:
            return _fail(problem)
        assert frame is not None
        opcode = int(frame["opcode"])
        payload = bytes(frame["payload"])
        fin = bool(frame["fin"])
        if opcode in _CONTROL:
            control, problem = _control(opcode, payload)
            if problem:
                return _fail(problem)
            controls.append(control)
            index = nxt
            continue
        if opcode == 0:
            if pending is None:
                return _fail("continuation")
            merged = bytearray(pending["data"])  # type: ignore[arg-type]
            merged.extend(payload)
            if len(merged) > _MAX_MESSAGE:
                return _fail("too-large")
            if not fin:
                pending["data"] = merged
                index = nxt
                continue
            emitted, problem = _emit(str(pending["kind"]), bytes(merged))
            if problem:
                return _fail(problem)
            messages.append(emitted)
            pending = None
            index = nxt
            continue
        if pending is not None:
            return _fail("fragment")
        kind = "text" if opcode == 1 else "binary"
        if not fin:
            if len(payload) > _MAX_MESSAGE:
                return _fail("too-large")
            pending = {"kind": kind, "data": bytearray(payload)}
            pending_at = index
            index = nxt
            continue
        emitted, problem = _emit(kind, payload)
        if problem:
            return _fail(problem)
        messages.append(emitted)
        index = nxt
    if pending is not None:
        return _partial(messages, controls, pending_at, pending)
    return _ok(messages, controls, index, "")


def _partial(
    messages: list[dict[str, object]],
    controls: list[dict[str, object]],
    consumed: int,
    pending: dict[str, object] | None,
) -> dict[str, object]:
    if not messages and not controls and pending is None:
        return _fail("truncated")
    if pending is not None and not messages and not controls:
        return _fail("truncated")
    return _ok(messages, controls, consumed, "truncated")


def _emit(kind: str, payload: bytes) -> tuple[dict[str, object] | None, str]:
    if kind == "binary":
        return {"kind": "binary", "data": payload}, ""
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return None, "utf8"
    return {"kind": "text", "data": text}, ""


def _control(opcode: int, payload: bytes) -> tuple[dict[str, object], str]:
    if opcode == 9:
        return {"kind": "ping", "data": payload, "code": None}, ""
    if opcode == 10:
        return {"kind": "pong", "data": payload, "code": None}, ""
    if len(payload) == 1:
        return {}, "close"
    code: int | None = None
    reason = b""
    if len(payload) >= 2:
        code = int.from_bytes(payload[:2], "big")
        reason = payload[2:]
        if code < 1000 or code > 4999 or code in _FORBIDDEN_CLOSE:
            return {}, "close"
        try:
            reason.decode("utf-8")
        except UnicodeDecodeError:
            return {}, "close"
    return {"kind": "close", "data": reason, "code": code}, ""


def _frame(data: bytes, index: int, sender: str) -> tuple[dict[str, object] | None, int, str]:
    size = len(data)
    if index + 2 > size:
        return None, index, "truncated"
    first = data[index]
    second = data[index + 1]
    if first & 0x70:
        return None, index, "rsv"
    opcode = first & 0x0F
    fin = bool(first & 0x80)
    masked = bool(second & 0x80)
    length = second & 0x7F
    cursor = index + 2
    if length == 126:
        if cursor + 2 > size:
            return None, index, "truncated"
        length = int.from_bytes(data[cursor : cursor + 2], "big")
        cursor += 2
        if length < 126:
            return None, index, "non-minimal-length"
    elif length == 127:
        if cursor + 8 > size:
            return None, index, "truncated"
        raw = data[cursor : cursor + 8]
        cursor += 8
        if raw[0] & 0x80:
            return None, index, "length"
        length = int.from_bytes(raw, "big")
        if length < 65536:
            return None, index, "non-minimal-length"
    if masked != (sender == "client"):
        return None, index, "mask"
    if opcode not in _DATA and opcode not in _CONTROL and opcode != 0:
        return None, index, "opcode"
    if opcode in _CONTROL:
        if not fin:
            return None, index, "control-fragment"
        if length > 125:
            return None, index, "control-length"
    if length > _MAX_MESSAGE:
        return None, index, "too-large"
    key = b""
    if masked:
        if cursor + 4 > size:
            return None, index, "truncated"
        key = data[cursor : cursor + 4]
        cursor += 4
    if cursor + length > size:
        return None, index, "truncated"
    payload = bytearray(data[cursor : cursor + length])
    if masked:
        for offset, byte in enumerate(payload):
            payload[offset] = byte ^ key[offset % 4]
    cursor += length
    return {"opcode": opcode, "fin": fin, "payload": bytes(payload)}, cursor, ""


def _ok(
    messages: list[dict[str, object]],
    controls: list[dict[str, object]],
    consumed: int,
    remainder: str,
) -> dict[str, object]:
    return {
        "ok": True,
        "error": "",
        "consumed": consumed,
        "messages": tuple(messages),
        "controls": tuple(controls),
        "remainder": remainder,
    }


def _fail(error: str) -> dict[str, object]:
    return {
        "ok": False,
        "error": error,
        "consumed": 0,
        "messages": (),
        "controls": (),
        "remainder": "",
    }
