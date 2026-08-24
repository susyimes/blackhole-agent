from __future__ import annotations

import pytest

from python_discovery._specifier import SimpleSpecifier, SimpleSpecifierSet, SimpleVersion

# --- SimpleVersion ---


@pytest.mark.parametrize(
    ("version_str", "release", "pre_type", "pre_num"),
    [
        pytest.param("3.11.2", (3, 11, 2), None, None, id="basic"),
        pytest.param("3.14.0a1", (3, 14, 0), "a", 1, id="alpha"),
        pytest.param("3.14.0b2", (3, 14, 0), "b", 2, id="beta"),
        pytest.param("3.14.0rc1", (3, 14, 0), "rc", 1, id="rc"),
        pytest.param("3", (3, 0, 0), None, None, id="major-only"),
        pytest.param("3.12", (3, 12, 0), None, None, id="major-minor"),
    ],
)
def test_version_parse(
    version_str: str,
    release: tuple[int, int, int],
    pre_type: str | None,
    pre_num: int | None,
) -> None:
    version = SimpleVersion.from_string(version_str)
    assert version.release == release
    assert version.pre_type == pre_type
    assert version.pre_num == pre_num


def test_version_invalid_raises() -> None:
    with pytest.raises(ValueError, match="Invalid version"):
        SimpleVersion.from_string("not_a_version")


def test_version_eq_same() -> None:
    assert SimpleVersion.from_string("3.11") == SimpleVersion.from_string("3.11")


def test_version_eq_different() -> None:
    assert SimpleVersion.from_string("3.11") != SimpleVersion.from_string("3.12")


def test_version_eq_not_implemented() -> None:
    result = SimpleVersion.from_string("3.11").__eq__("3.11")  # ruff:ignore[unnecessary-dunder-call]
    assert result is NotImplemented


def test_version_hash() -> None:
    assert hash(SimpleVersion.from_string("3.11")) == hash(SimpleVersion.from_string("3.11"))


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        pytest.param("3.11", "3.12", True, id="release"),
        pytest.param("3.14.0a1", "3.14.0", True, id="prerelease-vs-final"),
        pytest.param("3.14.0", "3.14.0a1", False, id="final-not-less-than-prerelease"),
        pytest.param("3.14.0", "3.14.0", False, id="equal"),
        pytest.param("3.14.0a1", "3.14.0b1", True, id="alpha-lt-beta"),
        pytest.param("3.14.0b1", "3.14.0rc1", True, id="beta-lt-rc"),
        pytest.param("3.14.0a1", "3.14.0a2", True, id="same-type-ordering"),
    ],
)
def test_version_lt(left: str, right: str, expected: bool) -> None:
    assert (SimpleVersion.from_string(left) < SimpleVersion.from_string(right)) is expected


def test_version_lt_not_implemented() -> None:
    result = SimpleVersion.from_string("3.11").__lt__("3.12")  # ruff:ignore[unnecessary-dunder-call]
    assert result is NotImplemented


def test_version_le() -> None:
    assert SimpleVersion.from_string("3.11") <= SimpleVersion.from_string("3.12")
    assert SimpleVersion.from_string("3.11") <= SimpleVersion.from_string("3.11")


def test_version_gt() -> None:
    assert SimpleVersion.from_string("3.12") > SimpleVersion.from_string("3.11")


def test_version_gt_not_implemented() -> None:
    result = SimpleVersion.from_string("3.11").__gt__("3.11")  # ruff:ignore[unnecessary-dunder-call]
    assert result is NotImplemented


def test_version_ge() -> None:
    assert SimpleVersion.from_string("3.12") >= SimpleVersion.from_string("3.11")
    assert SimpleVersion.from_string("3.12") >= SimpleVersion.from_string("3.12")


def test_version_str() -> None:
    assert str(SimpleVersion.from_string("3.11")) == "3.11"


def test_version_repr() -> None:
    assert repr(SimpleVersion.from_string("3.11")) == "SimpleVersion('3.11')"


# --- SimpleSpecifier ---


def test_specifier_invalid_raises() -> None:
    with pytest.raises(ValueError, match="Invalid specifier"):
        SimpleSpecifier.from_string("no_operator")


def test_specifier_parse_gte() -> None:
    spec = SimpleSpecifier.from_string(">=3.12")
    assert spec.operator == ">="
    assert spec.version == SimpleVersion.from_string("3.12")
    assert spec.is_wildcard is False


def test_specifier_parse_wildcard() -> None:
    spec = SimpleSpecifier.from_string("==3.11.*")
    assert spec.is_wildcard is True
    assert spec.wildcard_precision == 2


@pytest.mark.parametrize(
    ("spec_str", "version_str", "expected"),
    [
        pytest.param("==3.11.*", "3.11.5", True, id="wildcard-eq-match"),
        pytest.param("==3.11.*", "3.12.0", False, id="wildcard-eq-no-match"),
        pytest.param("!=3.11.*", "3.11.5", False, id="wildcard-ne-match"),
        pytest.param("!=3.11.*", "3.12.0", True, id="wildcard-ne-no-match"),
        pytest.param(">=3.11.*", "3.11.5", False, id="wildcard-unsupported-op"),
        pytest.param(">=3.12", "3.12.0", True, id="gte-match"),
        pytest.param(">=3.12", "3.13.0", True, id="gte-above"),
        pytest.param(">=3.12", "3.11.0", False, id="gte-below"),
        pytest.param("<=3.12", "3.12.0", True, id="lte-match"),
        pytest.param("<=3.12", "3.11.0", True, id="lte-below"),
        pytest.param("<=3.12", "3.13.0", False, id="lte-above"),
        pytest.param(">3.12", "3.13.0", True, id="gt-above"),
        pytest.param(">3.12", "3.12.0", False, id="gt-equal"),
        pytest.param("<3.12", "3.11.0", True, id="lt-below"),
        pytest.param("<3.12", "3.12.0", False, id="lt-equal"),
        pytest.param("==3.12.0", "3.12.0", True, id="eq-match"),
        pytest.param("==3.12.0", "3.12.1", False, id="eq-no-match"),
        pytest.param("!=3.12.0", "3.12.0", False, id="ne-match"),
        pytest.param("!=3.12.0", "3.12.1", True, id="ne-no-match"),
        pytest.param("===3.12", "3.12", True, id="exact-match"),
        pytest.param("===3.12", "3.12.0", False, id="exact-no-match"),
        pytest.param("~=3.12.0", "3.12.5", True, id="compatible-above"),
        pytest.param("~=3.12.0", "3.13.0", False, id="compatible-next-minor"),
        pytest.param("~=3.12.0", "3.11.0", False, id="compatible-below"),
        pytest.param("~=3.12.0", "3.11.9", False, id="compatible-just-below"),
        pytest.param(">=3.12", "not_a_version", False, id="invalid-version"),
    ],
)
def test_specifier_contains(spec_str: str, version_str: str, expected: bool) -> None:
    spec = SimpleSpecifier.from_string(spec_str)
    assert spec.contains(version_str) is expected


def test_specifier_contains_version_none() -> None:
    spec = SimpleSpecifier(
        spec_str=">=3.12",
        operator=">=",
        version_str="3.12",
        is_wildcard=False,
        wildcard_precision=None,
        version=None,
    )
    assert spec.contains("3.12") is False


def test_specifier_wildcard_version_none() -> None:
    spec = SimpleSpecifier(
        spec_str="==3.11.*",
        operator="==",
        version_str="3.11",
        is_wildcard=True,
        wildcard_precision=2,
        version=None,
    )
    assert spec.contains("3.11.0") is False


def test_specifier_compatible_release_version_none() -> None:
    spec = SimpleSpecifier(
        spec_str="~=3.12",
        operator="~=",
        version_str="3.12",
        is_wildcard=False,
        wildcard_precision=None,
        version=None,
    )
    assert spec._check_compatible_release(SimpleVersion.from_string("3.12")) is False


def test_specifier_eq() -> None:
    assert SimpleSpecifier.from_string(">=3.12") == SimpleSpecifier.from_string(">=3.12")


def test_specifier_eq_not_implemented() -> None:
    result = SimpleSpecifier.from_string(">=3.12").__eq__(">=3.12")  # ruff:ignore[unnecessary-dunder-call]
    assert result is NotImplemented


def test_specifier_hash() -> None:
    assert hash(SimpleSpecifier.from_string(">=3.12")) == hash(SimpleSpecifier.from_string(">=3.12"))


def test_specifier_str() -> None:
    assert str(SimpleSpecifier.from_string(">=3.12")) == ">=3.12"


def test_specifier_repr() -> None:
    assert repr(SimpleSpecifier.from_string(">=3.12")) == "SimpleSpecifier('>=3.12')"


def test_specifier_version_parse_failure_stores_none() -> None:
    spec = SimpleSpecifier.from_string(">=abc.*")
    assert spec.version is None


def test_specifier_unknown_operator() -> None:
    spec = SimpleSpecifier(
        spec_str="??3.12",
        operator="??",
        version_str="3.12",
        is_wildcard=False,
        wildcard_precision=None,
        version=SimpleVersion.from_string("3.12"),
    )
    assert spec.contains("3.12.0") is False


# --- SimpleSpecifierSet ---


@pytest.mark.parametrize(
    ("spec_str", "version_str", "expected"),
    [
        pytest.param("", "3.12", True, id="empty-always-matches"),
        pytest.param(">=3.12", "3.12.0", True, id="single-match"),
        pytest.param(">=3.12", "3.11.0", False, id="single-no-match"),
        pytest.param(">=3.12,<3.14", "3.12.0", True, id="compound-lower-bound"),
        pytest.param(">=3.12,<3.14", "3.13.0", True, id="compound-middle"),
        pytest.param(">=3.12,<3.14", "3.14.0", False, id="compound-upper-bound"),
        pytest.param(">=3.12,<3.14", "3.11.0", False, id="compound-below"),
    ],
)
def test_specifier_set_contains(spec_str: str, version_str: str, expected: bool) -> None:
    spec_set = SimpleSpecifierSet.from_string(spec_str)
    assert spec_set.contains(version_str) is expected


def test_specifier_set_iter() -> None:
    spec_set = SimpleSpecifierSet.from_string(">=3.12,<3.14")
    specs = list(spec_set)
    assert len(specs) == 2


def test_specifier_set_eq() -> None:
    assert SimpleSpecifierSet.from_string(">=3.12") == SimpleSpecifierSet.from_string(">=3.12")


def test_specifier_set_eq_not_implemented() -> None:
    result = SimpleSpecifierSet.from_string(">=3.12").__eq__(">=3.12")  # ruff:ignore[unnecessary-dunder-call]
    assert result is NotImplemented


def test_specifier_set_hash() -> None:
    assert hash(SimpleSpecifierSet.from_string(">=3.12")) == hash(SimpleSpecifierSet.from_string(">=3.12"))


def test_specifier_set_str() -> None:
    assert str(SimpleSpecifierSet.from_string(">=3.12")) == ">=3.12"


def test_specifier_set_repr() -> None:
    assert repr(SimpleSpecifierSet.from_string(">=3.12")) == "SimpleSpecifierSet('>=3.12')"


def test_specifier_set_invalid_specifier_skipped() -> None:
    spec_set = SimpleSpecifierSet.from_string(">=3.12, invalid_spec")
    assert len(spec_set.specifiers) == 1


def test_specifier_set_contains_no_specifiers() -> None:
    spec_set = SimpleSpecifierSet.from_string()
    assert spec_set.contains("3.12") is True


def test_specifier_set_empty_item_in_comma_list() -> None:
    spec_set = SimpleSpecifierSet.from_string(">=3.12,,<3.14")
    assert len(spec_set.specifiers) == 2


def test_specifier_compatible_release_major_only() -> None:
    spec = SimpleSpecifier.from_string("~=3")
    assert spec.contains("3.0.0") is True
    assert spec.contains("3.0.5") is True
