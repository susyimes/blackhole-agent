"""External fixture tool: reverses text.

Contract: read a JSON state object on stdin, write a JSON fragment on stdout.
This simulates a third-party tool the absorption plane can vendor and wrap as
a first-class invocable ledger capability.
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    state = json.load(sys.stdin)
    text = str(state["raw_text"])
    json.dump({"reversed_text": text[::-1]}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
