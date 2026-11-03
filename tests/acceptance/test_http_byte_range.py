"""HTTP bytes ranges are satisfiable, unsatisfiable, or ignored.

An inclusive end past the representation is clamped. A suffix longer
than the representation is the whole representation. One satisfiable
range survives beside an unsatisfiable one, and overlapping ranges stay
uncoalesced. A last position before the first, a non-bytes unit, a
non-GET method, and a second Range line that repeats the unit are
ignored. A first position at the length and a zero suffix are 416.
A non-zero suffix of a zero-length representation is a partial whole.
A numeral past signed 64-bit range is ignored.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both
met and unmet outcomes.
"""

from __future__ import annotations

import json


def _one(length: int, value: str, method: str = "GET") -> dict:
    from blackhole_agent.http_byte_range import satisfy_byte_ranges

    return satisfy_byte_ranges(length, [("Range", value)], method=method)


def observe() -> tuple[bool, dict]:
    observed: dict = {"layer": "byte-range"}
    try:
        from blackhole_agent.http_byte_range import satisfy_byte_ranges
    except Exception as exc:  # noqa: BLE001 - baseline without the decider still exits 0
        observed["error"] = type(exc).__name__
        return False, observed

    try:
        first = _one(10000, "bytes=0-499")
        open_end = _one(10000, "bytes=9500-")
        suffix = _one(10000, "bytes=-500")
        short_suffix = _one(200, "bytes=-500")
        clamped = _one(200, "bytes=0-499")
        mixed = _one(10000, "bytes=0-499,10000-20000")
        ends = _one(10000, "bytes=0-0,-1")
        spaced = _one(10000, "bytes= 0-999, 4500-5499, -1000")
        overlap = _one(10000, "bytes=500-700,601-999")
        backwards = _one(10000, "bytes=500-400")
        mixed_backwards = _one(10000, "bytes=0-499,500-400")
        other_unit = _one(10000, "items=0-1")
        posted = _one(10000, "bytes=0-499", "POST")
        head = _one(10000, "bytes=0-499", "HEAD")
        at_length = _one(10000, "bytes=10000-")
        zero_suffix = _one(10000, "bytes=-0")
        empty_suffix = _one(0, "bytes=-1")
        empty_int = _one(0, "bytes=0-0")
        upper = _one(10000, "BYTES=0-499")
        continued = satisfy_byte_ranges(10, [("Range", "bytes=0-1"), ("X-Other", "no"), ("Range", "3-4")])
        repeated_unit = satisfy_byte_ranges(10, [("Range", "bytes=0-1"), ("Range", "bytes=3-4")])
        overflow = _one(10, "bytes=9223372036854775808-")
        int64_edge = _one(10, "bytes=9223372036854775807-")
        absent = satisfy_byte_ranges(10, [("Content-Type", "text/plain")])
    except Exception as exc:  # noqa: BLE001 - an unmet outcome still exits 0
        observed["error"] = type(exc).__name__
        return False, observed

    observed.update(
        {
            "first_status": first["status"],
            "first_ranges": first["ranges"],
            "first_content_range": first["content_range"],
            "open_end": open_end["ranges"],
            "suffix": suffix["ranges"],
            "short_suffix": short_suffix["ranges"],
            "clamped": clamped["ranges"],
            "clamped_content_range": clamped["content_range"],
            "mixed": mixed["ranges"],
            "mixed_content_range": mixed["content_range"],
            "ends": ends["ranges"],
            "ends_content_range": ends["content_range"],
            "ends_parts": ends["parts"],
            "spaced": spaced["ranges"],
            "overlap": overlap["ranges"],
            "backwards": backwards["decision"],
            "backwards_status": backwards["status"],
            "backwards_error": backwards["error"],
            "mixed_backwards": mixed_backwards["decision"],
            "other_unit": other_unit["error"],
            "posted": posted["error"],
            "head": head["error"],
            "at_length": at_length["status"],
            "at_length_content_range": at_length["content_range"],
            "zero_suffix": zero_suffix["status"],
            "zero_suffix_content_range": zero_suffix["content_range"],
            "empty_suffix_status": empty_suffix["status"],
            "empty_suffix_whole": empty_suffix["whole"],
            "empty_suffix_ranges": empty_suffix["ranges"],
            "empty_int": empty_int["status"],
            "empty_int_content_range": empty_int["content_range"],
            "upper": upper["ranges"],
            "continued": continued["ranges"],
            "repeated_unit": repeated_unit["decision"],
            "overflow": overflow["error"],
            "int64_edge": int64_edge["status"],
            "absent": absent["decision"],
        }
    )
    passed = (
        observed["first_status"] == 206
        and observed["first_ranges"] == [[0, 499]]
        and observed["first_content_range"] == "bytes 0-499/10000"
        and observed["open_end"] == [[9500, 9999]]
        and observed["suffix"] == [[9500, 9999]]
        and observed["short_suffix"] == [[0, 199]]
        and observed["clamped"] == [[0, 199]]
        and observed["clamped_content_range"] == "bytes 0-199/200"
        and observed["mixed"] == [[0, 499]]
        and observed["mixed_content_range"] == "bytes 0-499/10000"
        and observed["ends"] == [[0, 0], [9999, 9999]]
        and observed["ends_content_range"] == ""
        and observed["ends_parts"] == ["bytes 0-0/10000", "bytes 9999-9999/10000"]
        and observed["spaced"] == [[0, 999], [4500, 5499], [9000, 9999]]
        and observed["overlap"] == [[500, 700], [601, 999]]
        and observed["backwards"] == "ignored"
        and observed["backwards_status"] == 200
        and observed["backwards_error"] == "invalid"
        and observed["mixed_backwards"] == "ignored"
        and observed["other_unit"] == "unit"
        and observed["posted"] == "method"
        and observed["head"] == "method"
        and observed["at_length"] == 416
        and observed["at_length_content_range"] == "bytes */10000"
        and observed["zero_suffix"] == 416
        and observed["zero_suffix_content_range"] == "bytes */10000"
        and observed["empty_suffix_status"] == 206
        and observed["empty_suffix_whole"] is True
        and observed["empty_suffix_ranges"] == []
        and observed["empty_int"] == 416
        and observed["empty_int_content_range"] == "bytes */0"
        and observed["upper"] == [[0, 499]]
        and observed["continued"] == [[0, 1], [3, 4]]
        and observed["repeated_unit"] == "ignored"
        and observed["overflow"] == "invalid"
        and observed["int64_edge"] == 416
        and observed["absent"] == "absent"
    )
    return passed, observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"observed": observed, "passed": passed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
