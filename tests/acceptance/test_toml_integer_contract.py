"""An over-long TOML decimal integer is a decode error, not ValueError.

The standard-library parser still leaks ValueError. The contract parser and
each absorbed tomli slug must raise TOMLDecodeError for that literal, return
8 for a one-digit integer, and let a parse_float ValueError propagate.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import sys
import tomllib


def _kind(parser, document: str, *, parse_float=None) -> str:
    try:
        if parse_float is None:
            parser(document)
        else:
            parser(document, parse_float=parse_float)
    except Exception as exc:  # noqa: BLE001 - the outcome names the unexpected type
        # Vendored tomli and tomllib each define their own TOMLDecodeError.
        # Both subclass ValueError, so the class name is the contract signal.
        if type(exc).__name__ == "TOMLDecodeError":
            return "decode"
        if isinstance(exc, ValueError):
            return "value"
        return type(exc).__name__
    return "accepted"


def _bad_float(_text: str) -> float:
    raise ValueError("bad float")


def observe() -> tuple[bool, dict]:
    limit = sys.get_int_max_str_digits()
    overlong = "k = " + ("8" * (limit + 1))
    observed: dict = {
        "digit_limit": limit,
        "stdlib_overlong": _kind(tomllib.loads, overlong),
    }
    try:
        from blackhole_agent.toml_integer_contract import loads, vendored_loads, vendored_slugs
    except Exception as exc:  # noqa: BLE001 - baseline has no contract module
        observed["error"] = type(exc).__name__
        return False, observed

    def contract(document: str, *, parse_float=None):
        if parse_float is None:
            return loads(document)
        return loads(document, parse_float=parse_float)

    short = None
    short_error = ""
    try:
        short = loads("k = 8")["k"]
    except Exception as exc:  # noqa: BLE001 - unmet outcome stays observable
        short_error = type(exc).__name__
    observed.update(
        {
            "contract_overlong": _kind(contract, overlong),
            "contract_short": short,
            "contract_short_error": short_error,
            "contract_float": _kind(contract, "k = 1.5", parse_float=_bad_float),
            "slugs": {},
        }
    )
    for slug in vendored_slugs():
        def vendored(document: str, *, parse_float=None, slug: str = slug):
            if parse_float is None:
                return vendored_loads(slug, document)
            return vendored_loads(slug, document, parse_float=parse_float)

        slug_short = None
        slug_error = ""
        try:
            slug_short = vendored_loads(slug, "k = 8")["k"]
        except Exception as exc:  # noqa: BLE001 - one slug must not hide the others
            slug_error = f"{type(exc).__name__}: {exc}"[:180]
        observed["slugs"][slug] = {
            "overlong": _kind(vendored, overlong),
            "short": slug_short,
            "short_error": slug_error,
            "float": _kind(vendored, "k = 1.5", parse_float=_bad_float),
        }
    slug_rows = list(observed["slugs"].values())
    passed = bool(
        observed["stdlib_overlong"] == "value"
        and observed["contract_overlong"] == "decode"
        and observed["contract_short"] == 8
        and observed["contract_float"] == "value"
        and len(slug_rows) == 3
        and all(
            row["overlong"] == "decode" and row["short"] == 8 and row["float"] == "value"
            for row in slug_rows
        )
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
