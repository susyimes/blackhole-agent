"""A titled reference link and 6400 reference definitions render through marked.

The titled link keeps its href and title. The long document contains the first
and last anchors and finishes inside 1.2 seconds. The previous lexer rebuilt
the label list on every inline call and took about three seconds for the same
document. Prints JSON with boolean passed and nonempty observed. Exit 0 for
both met and unmet outcomes.
"""

from __future__ import annotations

import json
import time


_TITLE_DOC = '[a][b]\n\n[b]: /url "t"\n'
_TITLE_HTML = '<p><a href="/url" title="t">a</a></p>\n'
_DEFINITION_COUNT = 6400
_BUDGET_SECONDS = 1.2


def _definitions(count: int) -> str:
    refs = " ".join(f"[^{index}]" for index in range(count))
    defs = "\n".join(f"[^{index}]: x" for index in range(count))
    return refs + "\n\n" + defs


def observe() -> tuple[bool, dict]:
    observed: dict = {"definitions": _DEFINITION_COUNT, "budget_seconds": _BUDGET_SECONDS}
    try:
        from blackhole_agent.marked_reference_parse import parse_marked
    except Exception as exc:  # noqa: BLE001 - baseline without the parser still exits 0
        observed["error"] = type(exc).__name__
        return False, observed

    try:
        titled = parse_marked(_TITLE_DOC)
        observed["titled"] = titled
    except Exception as exc:  # noqa: BLE001 - unmet titled link stays observable
        observed["titled_error"] = type(exc).__name__
        observed["titled_detail"] = str(exc)[:300]
        return False, observed

    document = _definitions(_DEFINITION_COUNT)
    started = time.perf_counter()
    try:
        rendered = parse_marked(document)
    except Exception as exc:  # noqa: BLE001 - unmet long document stays observable
        observed["long_error"] = type(exc).__name__
        observed["long_detail"] = str(exc)[:300]
        observed["elapsed_seconds"] = round(time.perf_counter() - started, 4)
        return False, observed
    elapsed = time.perf_counter() - started
    first = ">^0</a>" in rendered
    last = f">^{_DEFINITION_COUNT - 1}</a>" in rendered
    observed.update(
        {
            "elapsed_seconds": round(elapsed, 4),
            "first_anchor": first,
            "last_anchor": last,
            "rendered_chars": len(rendered),
        }
    )
    passed = bool(
        titled == _TITLE_HTML
        and first
        and last
        and elapsed < _BUDGET_SECONDS
    )
    return passed, observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - unmet outcome must still exit 0
        passed = False
        observed = {"error": type(exc).__name__, "detail": str(exc)[:400]}
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
