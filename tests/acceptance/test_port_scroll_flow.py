"""Scroll a nested overflow port without moving its in-flow filler.

A 100px overflow:scroll port keeps a sticky child at x 10, y 45 until that
port's own offset changes. port_scroll (0, 30) moves the child to y 75, and
(20, 30) also moves it to x 30. The 200px filler stays at y 60. Viewport
scroll still leaves the child still and moves only the following sticky
block. A hit on the scrolled child is that child. A missing port, a negative
offset, and overflow:visible are rejected. A vertical-rl port stays unplaced.

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

_PAGE = (
    '<div id="page"><div id="lead"></div><div id="port"><div id="inner">I</div>'
    '<div id="fill"></div></div><div id="outer">O</div></div>'
)
_CSS = (
    "#page { height: 900px; margin: 0px; }\n"
    "#lead { height: 40px; margin: 0px; }\n"
    "#port { overflow: scroll; height: 100px; margin: 0px; }\n"
    "#inner { position: sticky; top: 5px; left: 10px; width: 40px; height: 20px; margin: 0px; }\n"
    "#fill { height: 200px; margin: 0px; }\n"
    "#outer { position: sticky; top: 0px; height: 20px; margin: 0px; }\n"
)
_VISIBLE = _CSS.replace("overflow: scroll;", "overflow: visible;", 1)
_VERTICAL = _CSS.replace(
    "#port { overflow: scroll; height: 100px; margin: 0px; }\n",
    "#port { overflow: scroll; height: 100px; margin: 0px; writing-mode: vertical-rl; }\n",
    1,
)


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


def _near(item: dict[str, object] | None, **expected: object) -> bool:
    if item is None:
        return False
    return all(item.get(key) == value for key, value in expected.items())


def _call(function, markup: str, stylesheet: str, **kwargs: object) -> dict[str, object]:
    attempt = dict(kwargs)
    try:
        result = function(markup, stylesheet, viewport_width=300, viewport_height=300, **attempt)
    except TypeError as exc:
        if "port_scroll" not in attempt or "port_scroll" not in str(exc):
            return {"outcome": "invalid", "reason": str(exc), "boxes": None, "id": None}
        attempt.pop("port_scroll", None)
        try:
            result = function(markup, stylesheet, viewport_width=300, viewport_height=300, **attempt)
        except TypeError as again:
            return {"outcome": "invalid", "reason": str(again), "boxes": None, "id": None}
        except Exception as exc:  # noqa: BLE001 - a raised retry is an unmet outcome
            return {
                "outcome": "error",
                "reason": f"{type(exc).__name__}: {exc}",
                "boxes": None,
                "id": None,
            }
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {
            "outcome": "error",
            "reason": f"{type(exc).__name__}: {exc}",
            "boxes": None,
            "id": None,
        }
    if not isinstance(result, dict):
        return {"outcome": "error", "reason": "layout is invalid", "boxes": None, "id": None}
    return result


def _point(result: dict[str, object], ident: str) -> dict[str, object] | None:
    box = _box(result.get("boxes"), ident)
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "border_width": box.get("border_width"),
        "border_height": box.get("border_height"),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        supply_html_parser()
        from blackhole_agent.css_normal_flow import element_from_document, layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    down = _call(layout_normal_flow, _PAGE, _CSS, port_scroll={"port": (0, 30)})
    across = _call(layout_normal_flow, _PAGE, _CSS, port_scroll={"port": (20, 30)})
    stopped = _call(layout_normal_flow, _PAGE, _CSS, port_scroll={"port": (0, 100)})
    viewport = _call(
        layout_normal_flow,
        _PAGE,
        _CSS,
        port_scroll={"port": (0, 0)},
        scroll_y=200,
    )
    missing = _call(layout_normal_flow, _PAGE, _CSS, port_scroll={"gone": (0, 10)})
    negative = _call(layout_normal_flow, _PAGE, _CSS, port_scroll={"port": (0, -1)})
    visible = _call(layout_normal_flow, _PAGE, _VISIBLE, port_scroll={"port": (0, 30)})
    vertical = _call(layout_normal_flow, _PAGE, _VERTICAL, port_scroll={"port": (0, 30)})
    hit_child = _call(element_from_document, _PAGE, _CSS, x=10, y=75, port_scroll={"port": (0, 30)})
    hit_gap = _call(element_from_document, _PAGE, _CSS, x=10, y=45, port_scroll={"port": (0, 30)})
    observed: dict[str, object] = {
        "down": {name: _point(down, name) for name in ("port", "inner", "fill", "outer")},
        "across": _point(across, "inner"),
        "stopped": _point(stopped, "inner"),
        "viewport": {name: _point(viewport, name) for name in ("inner", "outer", "fill")},
        "missing": missing.get("reason"),
        "negative": negative.get("reason"),
        "visible": visible.get("reason"),
        "vertical": vertical.get("reason"),
        "hit_child": hit_child.get("id"),
        "hit_gap": hit_gap.get("id"),
    }
    checks = {
        "down_inner": _near(_box(down.get("boxes"), "inner"), x=10, y=75, border_width=40, border_height=20),
        "down_fill": _near(_box(down.get("boxes"), "fill"), x=0, y=60, border_height=200),
        "down_port": _near(_box(down.get("boxes"), "port"), x=0, y=40, border_height=100),
        "down_outer": _near(_box(down.get("boxes"), "outer"), x=0, y=140, border_height=20),
        "across_inner": _near(_box(across.get("boxes"), "inner"), x=30, y=75, border_width=40, border_height=20),
        "across_fill": _near(_box(across.get("boxes"), "fill"), y=60),
        "stopped_inner": _near(_box(stopped.get("boxes"), "inner"), x=10, y=120, border_height=20),
        "viewport_inner": _near(_box(viewport.get("boxes"), "inner"), x=10, y=45, border_height=20),
        "viewport_outer": _near(_box(viewport.get("boxes"), "outer"), y=200),
        "viewport_fill": _near(_box(viewport.get("boxes"), "fill"), y=60),
        "missing": missing.get("outcome") == "invalid" and missing.get("reason") == "scrollport is missing",
        "negative": negative.get("outcome") == "invalid" and negative.get("reason") == "port scroll is invalid",
        "visible": visible.get("outcome") == "invalid" and visible.get("reason") == "scrollport is not scrollable",
        "vertical": vertical.get("outcome") == "invalid" and vertical.get("boxes") is None,
        "hit_child": hit_child.get("outcome") == "hit" and hit_child.get("id") == "inner",
        "hit_gap": hit_gap.get("outcome") == "hit" and hit_gap.get("id") != "inner",
    }
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, separators=(",", ":")))


if __name__ == "__main__":
    main()
