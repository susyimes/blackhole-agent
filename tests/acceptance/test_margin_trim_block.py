"""Trim descendant margins that adjoin a block container's named edges.

margin-trim: block discards the first child's block-start margin and the
last child's block-end margin, including a grandchild margin collapsed
through the first child. The container's own margin and the collapsed gap
between siblings stay. block-start and block-end each trim one edge.
block-end block-start is the same pair as block. inline is not a value.
A vertical writing mode or columns with a trim is rejected.

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
_PAIR = (
    '<div id="page"><div id="hole"><div id="a">A</div><div id="b">B</div></div>'
    '<div id="next">Z</div></div>'
)
_NEST = (
    '<div id="page"><div id="hole"><div id="a"><div id="g">G</div></div></div>'
    '<div id="next">Z</div></div>'
)
_EDGES = "#a { margin-top: 30px; height: 10px; } #b { height: 10px; margin-bottom: 40px; }\n"


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


def _at(result: dict[str, object], ident: str) -> dict[str, object]:
    box = _box(result.get("boxes"), ident)
    return {
        "outcome": result.get("outcome"),
        "reason": result.get("reason"),
        "y": None if box is None else box.get("y"),
        "h": None if box is None else box.get("content_height"),
    }


def _lay(layout, html: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(html, _BASE + stylesheet, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _rejected(result: dict[str, object]) -> bool:
    return result.get("outcome") == "invalid" and result.get("boxes") is None


def observe() -> tuple[bool, dict[str, object]]:
    try:
        supply_html_parser()
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    cases = {
        "both": _lay(layout_normal_flow, _PAIR, "#hole { margin-trim: block-end block-start; }\n" + _EDGES),
        "start": _lay(layout_normal_flow, _PAIR, "#hole { margin-trim: block-start; }\n" + _EDGES),
        "end": _lay(layout_normal_flow, _PAIR, "#hole { margin-trim: block-end; }\n" + _EDGES),
        "own": _lay(
            layout_normal_flow,
            _PAIR,
            "#hole { margin-top: 12px; margin-trim: block-start; }\n"
            "#a { margin-top: 30px; height: 10px; } #b { height: 10px; }\n",
        ),
        "flow": _lay(
            layout_normal_flow,
            _PAIR,
            "#hole { display: flow-root; margin-trim: block; }\n" + _EDGES,
        ),
        "siblings": _lay(
            layout_normal_flow,
            _PAIR,
            "#hole { margin-trim: block; }\n"
            "#a { height: 10px; margin-bottom: 30px; } #b { height: 10px; margin-top: 10px; }\n",
        ),
        "grandchild": _lay(
            layout_normal_flow,
            _NEST,
            "#hole { margin-trim: block-start; }\n#g { margin-top: 30px; height: 10px; }\n",
        ),
        "inline": _lay(layout_normal_flow, _PAIR, "#hole { margin-trim: inline; }\n" + _EDGES),
        "vertical": _lay(
            layout_normal_flow,
            _PAIR,
            "#hole { margin-trim: block; writing-mode: vertical-rl; }\n" + _EDGES,
        ),
        "columns": _lay(
            layout_normal_flow,
            _PAIR,
            "#hole { margin-trim: block; column-count: 2; }\n" + _EDGES,
        ),
    }
    facts = {name: _at(result, "hole") for name, result in cases.items()}
    for name, ident in (
        ("both_a", "a"),
        ("both_b", "b"),
        ("both_next", "next"),
        ("start_b", "b"),
        ("start_next", "next"),
        ("end_a", "a"),
        ("end_next", "next"),
        ("own_a", "a"),
        ("own_next", "next"),
        ("flow_a", "a"),
        ("flow_next", "next"),
        ("sib_b", "b"),
        ("sib_next", "next"),
        ("grand", "g"),
        ("grand_next", "next"),
    ):
        source = {
            "both_a": "both",
            "both_b": "both",
            "both_next": "both",
            "start_b": "start",
            "start_next": "start",
            "end_a": "end",
            "end_next": "end",
            "own_a": "own",
            "own_next": "own",
            "flow_a": "flow",
            "flow_next": "flow",
            "sib_b": "siblings",
            "sib_next": "siblings",
            "grand": "grandchild",
            "grand_next": "grandchild",
        }[name]
        facts[name] = _at(cases[source], ident)
    checks = {
        "block_discards_both_edge_margins": (
            facts["both"]["y"] == 0
            and facts["both"]["h"] == 20
            and facts["both_a"]["y"] == 0
            and facts["both_a"]["h"] == 10
            and facts["both_b"]["y"] == 10
            and facts["both_next"]["y"] == 20
        ),
        "block_start_keeps_the_end_margin": (
            facts["start"]["y"] == 0
            and facts["start"]["h"] == 20
            and facts["start_b"]["y"] == 10
            and facts["start_next"]["y"] == 60
        ),
        "block_end_keeps_the_start_margin": (
            facts["end"]["y"] == 30
            and facts["end"]["h"] == 20
            and facts["end_a"]["y"] == 30
            and facts["end_next"]["y"] == 50
        ),
        "the_container_margin_stays": (
            facts["own"]["y"] == 12
            and facts["own"]["h"] == 20
            and facts["own_a"]["y"] == 12
            and facts["own_next"]["y"] == 32
        ),
        "a_flow_root_drops_the_interior_edge_margins": (
            facts["flow"]["y"] == 0
            and facts["flow"]["h"] == 20
            and facts["flow_a"]["y"] == 0
            and facts["flow_next"]["y"] == 20
        ),
        "sibling_margins_still_collapse": (
            facts["siblings"]["h"] == 50
            and facts["sib_b"]["y"] == 40
            and facts["sib_next"]["y"] == 50
        ),
        "a_collapsed_grandchild_margin_is_discarded": (
            facts["grandchild"]["y"] == 0
            and facts["grandchild"]["h"] == 10
            and facts["grand"]["y"] == 0
            and facts["grand_next"]["y"] == 10
        ),
        "inline_is_invalid": _rejected(cases["inline"]),
        "vertical_trim_is_rejected": _rejected(cases["vertical"]),
        "column_trim_is_rejected": _rejected(cases["columns"]),
    }
    return all(checks.values()), {"checks": checks, "facts": facts}


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
