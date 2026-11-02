"""Parse Markdown with the absorbed marked lexer.

The vendored lexer rebuilt its reference-label list on every inline call,
including link text that cannot contain a reference. ``parse_marked`` renders
through that lexer after the list is built once per bracketed source and
consulted as a set.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

_NODE_SCRIPT = """\
import {{ marked }} from {specifier};
import {{ readFileSync }} from "node:fs";
process.stdout.write(marked.parse(readFileSync(0, "utf8")));
"""


def marked_esm_path() -> Path:
    """Return the absorbed marked build this parser executes."""

    return (
        Path(__file__).resolve().parents[2]
        / "capabilities"
        / "absorbed"
        / "marked"
        / "package"
        / "lib"
        / "marked.esm.js"
    )


def parse_marked(text: str, *, timeout: float = 30.0) -> str:
    """Render ``text`` to HTML with the absorbed marked lexer."""

    esm = marked_esm_path()
    node = shutil.which("node")
    if node is None or not esm.is_file():
        raise FileNotFoundError("absorbed marked lexer is unavailable")
    completed = subprocess.run(
        [node, "--input-type=module", "-e", _NODE_SCRIPT.format(specifier=json.dumps(esm.as_uri()))],
        input=text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "marked failed").strip()
        raise RuntimeError(detail[-500:])
    return completed.stdout
