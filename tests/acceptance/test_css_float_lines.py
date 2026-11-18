"""Pack atomic inlines into line boxes shortened by float margin boxes.

A 100px containing block and a left float of 40 by 20 shorten the first two
10px lines to a 60px gap and restore the third line to the full width. Two
30px atoms share that gap. An 80px atom drops to the float bottom. A 110px
atom drops there and overflows. Left and right floats together leave 40px,
then 70px once the right float ends. A 50px atom drops only to the nearer
float bottom. A float as wide as the block drops the line instead of keeping
a zero-width box.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the packer still exits 0.
"""

from __future__ import annotations

import json
import sys


def _left(width: int, height: int, y: int = 0, x: int = 0) -> dict[str, int]:
    return {"side": "left", "x": x, "y": y, "width": width, "height": height}


def _right(x: int, width: int, height: int, y: int = 0) -> dict[str, int]:
    return {"side": "right", "x": x, "y": y, "width": width, "height": height}


def _atom(name: str, width: int) -> dict[str, object]:
    return {"id": name, "width": width}


def _line(x: int, y: int, width: int, atoms: list[str], height: int = 10) -> dict[str, object]:
    return {"x": x, "y": y, "width": width, "height": height, "atoms": atoms}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_float_lines import pack_line_boxes
    except Exception as exc:  # noqa: BLE001 - baseline without the packer still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def take(name: str, **kwargs: object) -> dict[str, object]:
        try:
            result = pack_line_boxes(**kwargs)
        except Exception as exc:  # noqa: BLE001 - a raised pack is an unmet outcome
            result = {"outcome": "error", "lines": None, "reason": f"{type(exc).__name__}: {exc}"}
        packed = result if isinstance(result, dict) else {"outcome": "error", "lines": None}
        observed[name] = {
            "outcome": packed.get("outcome"),
            "lines": packed.get("lines"),
            "reason": packed.get("reason"),
        }
        return observed[name]

    def expect(name: str, lines: list[dict[str, object]], **kwargs: object) -> None:
        got = take(name, **kwargs)
        checks.append(got.get("outcome") == "placed" and got.get("lines") == lines)

    left = _left(40, 20)
    expect(
        "split",
        [
            _line(40, 0, 60, ["a"]),
            _line(40, 10, 60, ["b"]),
            _line(0, 20, 100, ["c"]),
        ],
        containing_width=100,
        atoms=[_atom("a", 40), _atom("b", 40), _atom("c", 40)],
        floats=[left],
        line_height=10,
    )
    expect(
        "share",
        [_line(40, 0, 60, ["a", "b"])],
        containing_width=100,
        atoms=[_atom("a", 30), _atom("b", 30)],
        floats=[left],
        line_height=10,
    )
    expect(
        "drop",
        [_line(0, 20, 100, ["wide"])],
        containing_width=100,
        atoms=[_atom("wide", 80)],
        floats=[left],
        line_height=10,
    )
    expect(
        "overflow",
        [_line(0, 20, 100, ["over"])],
        containing_width=100,
        atoms=[_atom("over", 110)],
        floats=[left],
        line_height=10,
    )
    expect(
        "both",
        [
            _line(30, 0, 40, ["a"]),
            _line(30, 10, 40, ["b"]),
            _line(30, 20, 70, ["c"]),
        ],
        containing_width=100,
        atoms=[_atom("a", 40), _atom("b", 40), _atom("c", 40)],
        floats=[_left(30, 30), _right(70, 30, 15)],
        line_height=10,
    )
    expect(
        "near_bottom",
        [_line(40, 12, 60, ["a"])],
        containing_width=100,
        atoms=[_atom("a", 50)],
        floats=[_left(40, 40), _right(70, 30, 12)],
        line_height=10,
    )
    expect(
        "full",
        [_line(0, 10, 100, ["a"])],
        containing_width=100,
        atoms=[_atom("a", 40)],
        floats=[_left(100, 10)],
        line_height=10,
    )
    empty = take("empty", containing_width=100, atoms=[], floats=[], line_height=10)
    checks.append(empty.get("outcome") == "placed" and empty.get("lines") == [])
    bad = take("bad_width", containing_width=-1, atoms=[], floats=[], line_height=10)
    checks.append(bad.get("outcome") == "invalid" and bad.get("lines") is None and bool(bad.get("reason")))
    bad_bool = take(
        "bad_bool",
        containing_width=100,
        atoms=[{"id": "a", "width": True}],
        floats=[],
        line_height=10,
    )
    checks.append(bad_bool.get("outcome") == "invalid" and bad_bool.get("lines") is None)

    return all(checks), observed


def _emit(payload: dict[str, object]) -> None:
    """Write one ASCII JSON line. Isolated Windows runs use a GBK stdout."""

    try:
        line = json.dumps(payload, ensure_ascii=True)
    except Exception as exc:  # noqa: BLE001 - the probe must still emit a record
        line = json.dumps({"passed": False, "observed": {"error": f"{type(exc).__name__}: {exc}"}})
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        buffer.write(line.encode("ascii") + b"\n")
        buffer.flush()
        return
    print(line)


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    if not observed:
        observed = {"error": "empty observation"}
    _emit({"passed": bool(passed), "observed": observed})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
