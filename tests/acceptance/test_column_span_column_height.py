"""Place column-span all inside a fixed column-height row.

A 10px box, a 12px spanner, and a later 10px box keep the 30px rows: the
spanner uses the full content width at y 40, the later box starts at y 80,
and the next block starts at y 110. A leading spanner stays in the first
row. A 40px spanner in a 20px column overflows that row, and a 50px spanner
does not push the following row past the row gap.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

_BASE = (
    "html, body, div { margin: 0px; }\n"
    "#page { font-size: 10px; line-height: 10px; width: 200px; }\n"
    "#next { height: 8px; }\n"
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


def _markup(ids: str) -> str:
    children = "".join(f'<div id="{ident}"></div>' for ident in ids.split())
    return f'<div id="page"><div id="cols">{children}</div><div id="next"></div></div>'


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _view(result: dict[str, object], ident: str) -> dict[str, object] | None:
    box = _box(result.get("boxes"), ident)
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "content_width": box.get("content_width"),
        "content_height": box.get("content_height"),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        supply_html_parser()
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    between = _lay(
        layout_normal_flow,
        _markup("a s b"),
        _BASE
        + "#cols { column-count: 2; column-gap: 0px; column-height: 30px; row-gap: 10px; width: 80px; }\n"
        + "#a, #b { height: 10px; }\n#s { height: 12px; column-span: all; }\n",
    )
    leading = _lay(
        layout_normal_flow,
        _markup("s b"),
        _BASE
        + "#cols { column-count: 2; column-gap: 0px; column-height: 30px; row-gap: 10px; width: 80px; }\n"
        + "#b { height: 10px; }\n#s { height: 12px; column-span: all; }\n",
    )
    overflow = _lay(
        layout_normal_flow,
        _markup("s"),
        _BASE
        + "#cols { column-count: 2; column-gap: 0px; column-height: 20px; row-gap: 10px; width: 80px; }\n"
        + "#s { height: 40px; column-span: all; }\n",
    )
    crossed = _lay(
        layout_normal_flow,
        _markup("s a"),
        _BASE
        + "#cols { column-count: 2; column-gap: 0px; column-height: 30px; row-gap: 10px; width: 80px; }\n"
        + "#a { height: 10px; }\n#s { height: 50px; column-span: all; }\n",
    )

    def take(result: dict[str, object], ident: str) -> dict[str, object] | None:
        return _box(result.get("boxes"), ident)

    observed: dict[str, object] = {
        "between_outcome": between.get("outcome"),
        "between_reason": between.get("reason"),
        "between_a": _view(between, "a"),
        "between_s": _view(between, "s"),
        "between_b": _view(between, "b"),
        "between_cols": _view(between, "cols"),
        "between_next_y": None if take(between, "next") is None else take(between, "next").get("y"),
        "leading_s": _view(leading, "s"),
        "leading_b": _view(leading, "b"),
        "leading_cols": _view(leading, "cols"),
        "leading_next_y": None if take(leading, "next") is None else take(leading, "next").get("y"),
        "overflow_s": _view(overflow, "s"),
        "overflow_cols": _view(overflow, "cols"),
        "overflow_next_y": None if take(overflow, "next") is None else take(overflow, "next").get("y"),
        "crossed_s": _view(crossed, "s"),
        "crossed_a": _view(crossed, "a"),
        "crossed_cols": _view(crossed, "cols"),
        "crossed_next_y": None if take(crossed, "next") is None else take(crossed, "next").get("y"),
    }
    checks = {
        "spanner_between_boxes_keeps_each_row": (
            between.get("outcome") == "placed"
            and _near(take(between, "a"), x=0, y=0, content_width=40, content_height=10)
            and _near(take(between, "s"), x=0, y=40, content_width=80, content_height=12)
            and _near(take(between, "b"), x=0, y=80, content_width=40, content_height=10)
            and _near(take(between, "cols"), content_height=110)
            and _near(take(between, "next"), y=110)
        ),
        "leading_spanner_stays_in_the_first_row": (
            leading.get("outcome") == "placed"
            and _near(take(leading, "s"), x=0, y=0, content_width=80, content_height=12)
            and _near(take(leading, "b"), x=0, y=40, content_width=40, content_height=10)
            and _near(take(leading, "cols"), content_height=70)
            and _near(take(leading, "next"), y=70)
        ),
        "tall_spanner_overflows_without_growing_the_row": (
            overflow.get("outcome") == "placed"
            and _near(take(overflow, "s"), x=0, y=0, content_width=80, content_height=40)
            and _near(take(overflow, "cols"), content_height=20)
            and _near(take(overflow, "next"), y=20)
        ),
        "taller_spanner_does_not_push_the_next_row": (
            crossed.get("outcome") == "placed"
            and _near(take(crossed, "s"), x=0, y=0, content_width=80, content_height=50)
            and _near(take(crossed, "a"), x=0, y=40, content_width=40, content_height=10)
            and _near(take(crossed, "cols"), content_height=70)
            and _near(take(crossed, "next"), y=70)
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
