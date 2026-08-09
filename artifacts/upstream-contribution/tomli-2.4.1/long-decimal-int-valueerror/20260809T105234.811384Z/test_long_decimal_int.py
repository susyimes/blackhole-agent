"""Regression test for the long-decimal-int ValueError defect.

Authored in tomli's own test conventions (plain pytest function, public API
only) by blackhole_agent.upstream_contribution for the defect
`long-decimal-int-valueerror`: a decimal integer literal with more digits
than sys.get_int_max_str_digits() must surface as TOMLDecodeError (the API's
specified rejection of invalid input), not leak the int() conversion
ValueError (CVE-2020-10735 mitigation limit).
"""

import sys

import pytest

import tomli

OVERLONG = sys.get_int_max_str_digits() + 1 if hasattr(sys, "get_int_max_str_digits") else 0


@pytest.mark.skipif(OVERLONG == 0, reason="int string conversion limit exists on Python 3.11+")
def test_overlong_decimal_int_raises_decode_error():
    doc = "k = " + "8" * OVERLONG
    with pytest.raises(tomli.TOMLDecodeError):
        tomli.loads(doc)


@pytest.mark.skipif(OVERLONG == 0, reason="int string conversion limit exists on Python 3.11+")
def test_overlong_decimal_int_in_table_value_raises_decode_error():
    doc = "[t]\nk = " + "8" * OVERLONG
    with pytest.raises(tomli.TOMLDecodeError):
        tomli.loads(doc)
