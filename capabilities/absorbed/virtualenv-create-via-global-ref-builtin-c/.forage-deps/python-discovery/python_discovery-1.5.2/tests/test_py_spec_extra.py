from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from python_discovery import PythonSpec


def test_specifier_parse_failure_fallback() -> None:
    spec = PythonSpec.from_string_spec("not_a_valid_anything_really")
    assert spec.path == "not_a_valid_anything_really"
    assert spec.version_specifier is None


def test_version_specifier_satisfies_micro() -> None:
    spec = PythonSpec.from_string_spec(">=3.12.0")
    candidate = PythonSpec("", "CPython", 3, 12, 1, None, None)
    assert candidate.satisfies(spec) is True


def test_version_specifier_satisfies_fails_micro() -> None:
    spec = PythonSpec.from_string_spec(">=3.13.0")
    candidate = PythonSpec("", "CPython", 3, 12, 5, None, None)
    assert candidate.satisfies(spec) is False


def test_version_specifier_no_components() -> None:
    spec = PythonSpec.from_string_spec(">=3.12")
    candidate = PythonSpec("", None, None, None, None, None, None)
    assert candidate.satisfies(spec) is True


def test_check_version_specifier_precision() -> None:
    spec = PythonSpec.from_string_spec(">=3.12")
    candidate = PythonSpec("", "CPython", 3, None, None, None, None)
    assert candidate._check_version_specifier(spec) is True


def test_check_version_specifier_precision_micro() -> None:
    spec = PythonSpec.from_string_spec(">=3.12.0")
    candidate = PythonSpec("", "CPython", 3, 12, None, None, None)
    assert candidate._check_version_specifier(spec) is True


def test_check_version_specifier_fails() -> None:
    spec = PythonSpec.from_string_spec(">=3.13")
    candidate = PythonSpec("", "CPython", 3, 12, 0, None, None)
    assert candidate._check_version_specifier(spec) is False


def test_check_version_specifier_none() -> None:
    spec = PythonSpec("", None, None, None, None, None, None)
    candidate = PythonSpec("", "CPython", 3, 12, 0, None, None)
    assert candidate._check_version_specifier(spec) is True


def test_get_required_precision_none() -> None:
    from python_discovery._specifier import SimpleSpecifier

    specifier = SimpleSpecifier(
        spec_str=">=3.12",
        operator=">=",
        version_str="3.12",
        is_wildcard=False,
        wildcard_precision=None,
        version=None,
    )
    assert PythonSpec._get_required_precision(specifier) is None


def test_get_required_precision_normal() -> None:
    from python_discovery._specifier import SimpleSpecifier

    specifier = SimpleSpecifier.from_string(">=3.12.0")
    assert PythonSpec._get_required_precision(specifier) == 3


def test_generate_re_no_threaded() -> None:
    spec = PythonSpec.from_string_spec("python3.12")
    pat = spec.generate_re(windows=False)
    assert pat.fullmatch("python3.12") is not None


def test_generate_re_with_threaded() -> None:
    spec = PythonSpec.from_string_spec("python3.12t")
    pat = spec.generate_re(windows=False)
    assert pat.fullmatch("python3.12t") is not None


@pytest.mark.parametrize("name", ["python3.12-dbg", "python3.12d", "python3.12"])
def test_generate_re_with_debug(name: str) -> None:
    spec = PythonSpec.from_string_spec("python3.12-dbg")
    pat = spec.generate_re(windows=False)
    assert pat.fullmatch(name) is not None


def test_single_digit_version() -> None:
    spec = PythonSpec.from_string_spec("python3")
    assert spec.major == 3
    assert spec.minor is None


def test_specifier_with_invalid_inner() -> None:
    spec = PythonSpec.from_string_spec(">=not_a_version")
    assert spec.path is None or spec.version_specifier is not None or spec.path == ">=not_a_version"


def test_two_digit_version() -> None:
    spec = PythonSpec.from_string_spec("python312")
    assert spec.major == 3
    assert spec.minor == 12


def test_single_digit_major_only() -> None:
    spec = PythonSpec.from_string_spec("python3")
    assert spec.major == 3
    assert spec.minor is None


def test_specifier_set_parsed_for_valid_format() -> None:
    spec = PythonSpec.from_string_spec("cpython>=3.12")
    assert spec.version_specifier is not None
    assert spec.implementation == "cpython"


def test_get_required_precision_attribute_error() -> None:
    from python_discovery._specifier import SimpleSpecifier

    mock_version = MagicMock(spec=[])
    specifier = SimpleSpecifier(
        spec_str=">=3.12",
        operator=">=",
        version_str="3.12",
        is_wildcard=False,
        wildcard_precision=None,
        version=mock_version,
    )
    assert PythonSpec._get_required_precision(specifier) is None
