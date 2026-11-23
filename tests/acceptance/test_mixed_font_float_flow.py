"""Place mixed-size inline runs beside a rectangular float.

In a marginless 200px block, a 40 by 30 left float leaves AA at 20px and
Z at 10px on one line at x 40. AA is 40 wide, Z starts at x 80, the line
is 20 tall, the block content height is 30, and the next block starts at
y 30. In a 70px block that word does not fit beside the float, so the same
line starts at x 0, y 30 and the next block starts at y 50. A vertical-rl
block and a shaped float stay unplaced.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

_BASE = "html, body, div, p, i, b { margin: 0px; }\n"
_HTML = '<div id="page"><p id="mix"><i id="pin">F</i><b id="big">AA</b> Z</p><p id="next">Q</p></div>'
_WIDE = (
    "#page { width: 200px; font-size: 10px; line-height: 10px; }\n"
    "#pin { float: left; width: 40px; height: 30px; }\n"
    "#big { font-size: 20px; line-height: 20px; }\n"
    "#next { height: 10px; }\n"
)
_NARROW = (
    "#page { width: 70px; font-size: 10px; line-height: 10px; }\n"
    "#pin { float: left; width: 40px; height: 30px; }\n"
    "#big { font-size: 20px; line-height: 20px; }\n"
    "#next { height: 10px; }\n"
)
_VERTICAL = (
    "#page { width: 200px; writing-mode: vertical-rl; font-size: 10px; line-height: 10px; }\n"
    "#pin { float: left; width: 40px; height: 30px; }\n"
    "#big { font-size: 20px; line-height: 20px; }\n"
)
_SHAPED = (
    "#mix { font-size: 10px; line-height: 10px; }\n"
    "#pin { float: left; width: 40px; height: 30px; shape-outside: circle(20px at 20px 15px); }\n"
    "#big { font-size: 20px; line-height: 20px; }\n"
)
_RUNS = [
    {"text": "AA", "x": 40, "font_size": 20, "width": 40},
    {"text": " Z", "x": 80, "font_size": 10, "width": 20},
]


def supply_html_parser() -> None:
    """Restore the baseline's genuine runtime data to a src-only replay archive."""
    from blackhole_agent import html5_document

    package = html5_document._package_dir() / "html5lib"
    if (package / "__init__.py").is_file():
        return
    root = Path(html5_document.__file__).resolve().parents[2]
    if (root / ".git").exists() or not root.is_relative_to(Path(tempfile.gettempdir()).resolve()):
        raise RuntimeError("the checkout is missing its absorbed HTML parser")
    checkout = next((item.parent for item in map(Path, sys.path) if (item.parent / ".git").exists()), None)
    if checkout is None:
        raise RuntimeError("the replay requires the installed project's Git object database")
    tree = "397395a7d05f3f55ebd5bcb029a66b55bac0306b"
    archive = subprocess.check_output(["git", "-C", str(checkout), "archive", "--format=zip", tree], timeout=30)
    with zipfile.ZipFile(io.BytesIO(archive)) as files:
        files.extractall(package)


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _line(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None or not isinstance(box.get("lines"), list) or not box["lines"]:
        return None
    line = box["lines"][0]
    return line if isinstance(line, dict) else None


def _near(item: dict[str, object] | None, **expected: object) -> bool:
    if item is None:
        return False
    return all(item.get(key) == value for key, value in expected.items())


def _lay(layout, stylesheet: str, markup: str = _HTML) -> dict[str, object]:
    try:
        placed = layout(markup, _BASE + stylesheet, viewport_width=400)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _facts(result: dict[str, object], ident: str) -> dict[str, object]:
    box = _box(result.get("boxes"), ident)
    line = _line(box)
    return {
        "outcome": result.get("outcome"),
        "reason": result.get("reason"),
        "x": None if box is None else box.get("x"),
        "y": None if box is None else box.get("y"),
        "content_width": None if box is None else box.get("content_width"),
        "content_height": None if box is None else box.get("content_height"),
        "line": None
        if line is None
        else {
            "text": line.get("text"),
            "x": line.get("x"),
            "y": line.get("y"),
            "height": line.get("height"),
            "content_width": line.get("content_width"),
            "runs": line.get("runs"),
        },
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        supply_html_parser()
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    wide = _lay(layout_normal_flow, _WIDE)
    narrow = _lay(layout_normal_flow, _NARROW)
    vertical = _lay(layout_normal_flow, _VERTICAL)
    shaped = _lay(layout_normal_flow, _SHAPED, '<p id="mix"><i id="pin">F</i><b id="big">AA</b> Z</p>')
    wide_line = _line(_box(wide.get("boxes"), "mix"))
    narrow_line = _line(_box(narrow.get("boxes"), "mix"))
    observed = {
        "wide": _facts(wide, "mix"),
        "pin": _facts(wide, "pin"),
        "next": _facts(wide, "next"),
        "narrow": _facts(narrow, "mix"),
        "narrow_next": _facts(narrow, "next"),
        "vertical_reason": vertical.get("reason"),
        "shaped_reason": shaped.get("reason"),
    }
    checks = {
        "wide_line": (
            wide.get("outcome") == "placed"
            and _near(_box(wide.get("boxes"), "pin"), x=0, y=0, content_width=40, content_height=30)
            and _near(_box(wide.get("boxes"), "mix"), content_width=200, content_height=30)
            and _near(
                wide_line,
                text="AA Z",
                x=40,
                y=0,
                height=20,
                content_width=60,
                runs=_RUNS,
            )
            and _near(_box(wide.get("boxes"), "next"), x=0, y=30, content_height=10)
        ),
        "narrow_clears": (
            narrow.get("outcome") == "placed"
            and _near(_box(narrow.get("boxes"), "mix"), content_width=70, content_height=50)
            and _near(
                narrow_line,
                text="AA Z",
                x=0,
                y=30,
                height=20,
                content_width=60,
                runs=[
                    {"text": "AA", "x": 0, "font_size": 20, "width": 40},
                    {"text": " Z", "x": 40, "font_size": 10, "width": 20},
                ],
            )
            and _near(_box(narrow.get("boxes"), "next"), y=50, content_height=10)
        ),
        "vertical_rejected": vertical.get("outcome") == "invalid" and vertical.get("boxes") is None,
        "shaped_rejected": (
            shaped.get("outcome") == "invalid"
            and shaped.get("boxes") is None
            and shaped.get("reason") == "inline font beside a shaped float is unsupported"
        ),
    }
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> None:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 even when it fails
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    payload = {"passed": bool(passed), "observed": observed if observed else {"error": "empty"}}
    try:
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    except (UnicodeEncodeError, TypeError) as exc:
        encoded = json.dumps(
            {"passed": False, "observed": {"error": f"{type(exc).__name__}: {exc}"}},
            separators=(",", ":"),
        ).encode("ascii")
    sys.stdout.buffer.write(encoded + b"\n")


if __name__ == "__main__":
    main()
