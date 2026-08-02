"""Absorption adapter: bridges the vendored mistune package to the JSON state contract.

Reads a JSON state object on stdin ({"markdown_source": str}) and writes a
JSON fragment on stdout ({"rendered_html": str}), rendered by the vendored
mistune package under ./src. Authored by the blackhole-agent absorption plane
at absorption time; covered by the vendored tree digest like any other file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import mistune  # noqa: E402


def main() -> int:
    state = json.load(sys.stdin)
    html = mistune.html(str(state["markdown_source"]))
    json.dump({"rendered_html": html}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
