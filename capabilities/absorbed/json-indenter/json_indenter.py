"""Uncooperative fixture package: ships no absorption manifest.

Used by the capability acquisition plane to prove that a package which never
heard of the absorption contract can still be staged, adapted, and absorbed.
"""

from __future__ import annotations

import json


def indent(document: str) -> str:
    """Parse *document* as JSON and re-emit it indented and key-sorted."""

    return json.dumps(json.loads(document), indent=2, sort_keys=True)
