"""A second footnote label is stored in the index map.

The label list rejects membership tests. Admission must still append SECOND,
store index 1, and emit footnote_ref index 2. Rendering two definitions
emits fn-1 and fn-2. A repeated label emits one footnote item. An unknown
label emits none. A heading stays the frozen absorption result.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json

_TWO = "see [^a] and [^b].\n\n[^a]: alpha\n\n[^b]: beta\n"
_REPEAT = "see [^a] and [^a].\n\n[^a]: alpha\n"
_MISSING = "see [^missing].\n"
_HEADING = "# Blackhole"


def observe() -> tuple[bool, dict]:
    try:
        from blackhole_agent.mistune_footnote_index import footnote_admission, render_markdown
    except Exception as exc:  # noqa: BLE001 - baseline has no footnote index module
        return False, {"error": type(exc).__name__, "detail": str(exc)[:300]}

    try:
        admission = footnote_admission()
        two = render_markdown(_TWO)
        repeat = render_markdown(_REPEAT)
        missing = render_markdown(_MISSING)
        heading = render_markdown(_HEADING)
    except Exception as exc:  # noqa: BLE001 - unmet outcome stays observable
        return False, {"error": type(exc).__name__, "detail": str(exc)[:400]}

    token = (admission.get("tokens") or [{}])[0]
    observed = {
        "admission_error": admission.get("error"),
        "notes": admission.get("notes"),
        "indexes": admission.get("indexes"),
        "token": token,
        "two_has_fn1": 'id="fn-1"' in two,
        "two_has_fn2": 'id="fn-2"' in two,
        "two_alpha": "alpha" in two,
        "two_beta": "beta" in two,
        "repeat_items": repeat.count('<li id="fn-1">'),
        "repeat_alpha": repeat.count("alpha"),
        "missing_items": missing.count('<li id="fn-'),
        "heading": heading,
    }
    indexes = observed["indexes"] if isinstance(observed["indexes"], dict) else {}
    passed = bool(
        observed["admission_error"] == ""
        and observed["notes"] == ["FIRST", "SECOND"]
        and indexes.get("SECOND") == 1
        and token.get("type") == "footnote_ref"
        and token.get("raw") == "SECOND"
        and (token.get("attrs") or {}).get("index") == 2
        and observed["two_has_fn1"]
        and observed["two_has_fn2"]
        and observed["two_alpha"]
        and observed["two_beta"]
        and observed["repeat_items"] == 1
        and observed["repeat_alpha"] == 1
        and observed["missing_items"] == 0
        and observed["heading"] == "<h1>Blackhole</h1>\n"
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
