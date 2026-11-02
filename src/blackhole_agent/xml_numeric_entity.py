"""Parse XML with the absorbed fast-xml-parser bundle.

fast-xml-parser 5.2.5 feeds every HTML numeric character reference to
``String.fromCodePoint``. A code point above U+10FFFF, such as ``&#9999999;``
or ``&#xFFFFFF;``, raises ``RangeError`` and aborts the parse. The upstream
5.3.4 repair keeps an out-of-range reference as its original text and still
decodes a reference inside the Unicode range.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

_NODE_SCRIPT = """\
const { XMLParser } = require(process.argv[1]);
const xml = require("fs").readFileSync(0, "utf8");
const parser = new XMLParser({ htmlEntities: true, ignoreAttributes: false });
process.stdout.write(JSON.stringify(parser.parse(xml)));
"""


def xml_parser_bundle() -> Path:
    """Return the absorbed CommonJS bundle this parser executes."""

    return (
        Path(__file__).resolve().parents[2]
        / "capabilities"
        / "absorbed"
        / "fast-xml-parser"
        / "package"
        / "lib"
        / "fxp.cjs"
    )


def parse_xml(text: str, *, timeout: float = 30.0) -> Any:
    """Parse ``text`` with HTML numeric character references enabled.

    An in-range reference becomes its character. An out-of-range reference
    stays as the original ``&#...;`` text. ``RangeError`` is not an acceptable
    result.
    """

    bundle = xml_parser_bundle()
    node = shutil.which("node")
    if node is None or not bundle.is_file():
        raise FileNotFoundError("absorbed fast-xml-parser bundle is unavailable")
    completed = subprocess.run(
        [node, "-e", _NODE_SCRIPT, str(bundle)],
        input=text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "xml parser failed").strip()
        raise RuntimeError(detail[-500:])
    return json.loads(completed.stdout)
