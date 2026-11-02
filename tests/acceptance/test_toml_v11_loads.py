"""The public TOML loader accepts a TOML 1.1 document tomllib rejects.

A multiline inline table with a trailing comma, a ``\\e`` escape, a ``\\xHH``
escape, and a clock time without seconds parse to their values. An over-long
decimal integer and an unknown escape stay decode errors, a one-digit integer
stays 8, and a parse_float ValueError still propagates. tomllib rejects the
same 1.1 document.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import sys
import tomllib


_DOCUMENT = """\
csi = "\\e["
letter = "\\x61"
when = 14:15
moment = 2010-02-03 14:15
tbl = {
  key = "a string",
  nested = { n = 1, },
}
"""


def _kind(parser, document: str, *, parse_float=None) -> str:
    try:
        if parse_float is None:
            parser(document)
        else:
            parser(document, parse_float=parse_float)
    except Exception as exc:  # noqa: BLE001 - the outcome names the unexpected type
        if type(exc).__name__ == "TOMLDecodeError":
            return "decode"
        if isinstance(exc, ValueError):
            return "value"
        return type(exc).__name__
    return "accepted"


def _bad_float(_text: str) -> float:
    raise ValueError("bad float")


def _stdlib_kind(document: str) -> str:
    try:
        tomllib.loads(document)
    except tomllib.TOMLDecodeError:
        return "decode"
    except Exception as exc:  # noqa: BLE001 - peer outcome stays observable
        return type(exc).__name__
    return "accepted"


def observe() -> tuple[bool, dict]:
    observed: dict = {"stdlib": _stdlib_kind(_DOCUMENT)}
    try:
        from blackhole_agent.toml_integer_contract import loads
    except Exception as exc:  # noqa: BLE001 - baseline without the loader still exits 0
        observed["error"] = type(exc).__name__
        return False, observed

    try:
        parsed = loads(_DOCUMENT)
        when = parsed["when"]
        moment = parsed["moment"]
        observed.update(
            {
                "csi": parsed["csi"],
                "letter": parsed["letter"],
                "when": [when.hour, when.minute, when.second],
                "moment": [moment.year, moment.month, moment.day, moment.hour, moment.minute],
                "key": parsed["tbl"]["key"],
                "nested": parsed["tbl"]["nested"]["n"],
            }
        )
    except Exception as exc:  # noqa: BLE001 - unmet 1.1 parse stays observable
        observed["parse"] = type(exc).__name__

    limit = sys.get_int_max_str_digits()
    overlong = "k = " + ("8" * (limit + 1))
    short = None
    short_error = ""
    try:
        short = loads("k = 8")["k"]
    except Exception as exc:  # noqa: BLE001 - unmet short integer stays observable
        short_error = type(exc).__name__
    observed.update(
        {
            "digit_limit": limit,
            "overlong": _kind(loads, overlong),
            "bad_escape": _kind(loads, 'bad = "\\q"'),
            "short": short,
            "short_error": short_error,
            "float": _kind(loads, "k = 1.5", parse_float=_bad_float),
        }
    )
    passed = bool(
        observed["stdlib"] == "decode"
        and observed.get("csi") == "\u001b["
        and observed.get("letter") == "a"
        and observed.get("when") == [14, 15, 0]
        and observed.get("moment") == [2010, 2, 3, 14, 15]
        and observed.get("key") == "a string"
        and observed.get("nested") == 1
        and observed["overlong"] == "decode"
        and observed["bad_escape"] == "decode"
        and observed["short"] == 8
        and observed["float"] == "value"
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
