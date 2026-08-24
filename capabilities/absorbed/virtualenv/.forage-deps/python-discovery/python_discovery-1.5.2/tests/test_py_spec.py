from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from python_discovery import PythonSpec
from python_discovery._py_info import normalize_isa
from python_discovery._specifier import SimpleSpecifierSet as SpecifierSet

if TYPE_CHECKING:
    from pathlib import Path


def test_bad_py_spec() -> None:
    text = "python2.3.4.5"
    spec = PythonSpec.from_string_spec(text)
    assert text in repr(spec)
    assert spec.str_spec == text
    assert spec.path == text
    content = vars(spec)
    del content["str_spec"]
    del content["path"]
    assert all(v is None for v in content.values())


def test_py_spec_first_digit_only_major() -> None:
    spec = PythonSpec.from_string_spec("278")
    assert spec.major == 2
    assert spec.minor == 78


def test_spec_satisfies_path_ok() -> None:
    spec = PythonSpec.from_string_spec(sys.executable)
    assert spec.satisfies(spec) is True


def test_spec_satisfies_path_nok(tmp_path: pytest.TempPathFactory) -> None:
    spec = PythonSpec.from_string_spec(sys.executable)
    of = PythonSpec.from_string_spec(str(tmp_path))
    assert spec.satisfies(of) is False


def test_spec_satisfies_arch() -> None:
    spec_1 = PythonSpec.from_string_spec("python-32")
    spec_2 = PythonSpec.from_string_spec("python-64")

    assert spec_1.satisfies(spec_1) is True
    assert spec_2.satisfies(spec_1) is False


def test_spec_satisfies_free_threaded() -> None:
    spec_1 = PythonSpec.from_string_spec("python3.13t")
    spec_2 = PythonSpec.from_string_spec("python3.13")

    assert spec_1.satisfies(spec_1) is True
    assert spec_1.free_threaded is True
    assert spec_2.satisfies(spec_1) is False
    assert spec_2.free_threaded is False


@pytest.mark.parametrize(
    ("req", "spec"),
    [("py", "python"), ("jython", "jython"), ("CPython", "cpython")],
)
def test_spec_satisfies_implementation_ok(req: str, spec: str) -> None:
    spec_1 = PythonSpec.from_string_spec(req)
    spec_2 = PythonSpec.from_string_spec(spec)
    assert spec_1.satisfies(spec_1) is True
    assert spec_2.satisfies(spec_1) is True


def test_spec_satisfies_implementation_nok() -> None:
    spec_1 = PythonSpec.from_string_spec("cpython")
    spec_2 = PythonSpec.from_string_spec("jython")
    assert spec_2.satisfies(spec_1) is False
    assert spec_1.satisfies(spec_2) is False


def _version_satisfies_pairs() -> list[tuple[str, str]]:
    target: set[tuple[str, str]] = set()
    version = tuple(str(i) for i in sys.version_info[0:3])
    for threading in (False, True):
        for depth in range(len(version) + 1):
            req = ".".join(version[0:depth])
            for sub in range(depth + 1):
                sat = ".".join(version[0:sub])
                if sat:
                    target.add((req, sat))
                target.add((sat, req))
                if threading and sat and req:
                    target.add((f"{req}t", f"{sat}t"))
                    target.add((f"{sat}t", f"{req}t"))

    return sorted(target)


@pytest.mark.parametrize(("req", "spec"), _version_satisfies_pairs())
def test_version_satisfies_ok(req: str, spec: str) -> None:
    req_spec = PythonSpec.from_string_spec(f"python{req}")
    sat_spec = PythonSpec.from_string_spec(f"python{spec}")
    assert sat_spec.satisfies(req_spec) is True


def _version_not_satisfies_pairs() -> list[tuple[str, str]]:
    target: set[tuple[str, str]] = set()
    version = tuple(str(i) for i in sys.version_info[0:3])
    for major in range(len(version)):
        req = ".".join(version[0 : major + 1])
        for minor in range(major + 1):
            sat_ver: list[int] = [int(v) for v in sys.version_info[0 : minor + 1]]
            for patch in range(minor + 1):
                for offset in [1, -1]:
                    temp = sat_ver.copy()
                    temp[patch] += offset
                    if temp[patch] < 0:
                        continue  # pragma: no cover
                    sat = ".".join(str(i) for i in temp)
                    target.add((req, sat))
    return sorted(target)


@pytest.mark.parametrize(("req", "spec"), _version_not_satisfies_pairs())
def test_version_satisfies_nok(req: str, spec: str) -> None:
    req_spec = PythonSpec.from_string_spec(f"python{req}")
    sat_spec = PythonSpec.from_string_spec(f"python{spec}")
    assert sat_spec.satisfies(req_spec) is False


def test_relative_spec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    a_relative_path = str((tmp_path / "a" / "b").relative_to(tmp_path))
    spec = PythonSpec.from_string_spec(a_relative_path)
    assert spec.path == a_relative_path


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (">=3.12", ">=3.12"),
        ("python>=3.12", ">=3.12"),
        ("cpython!=3.11.*", "!=3.11.*"),
        ("<=3.13,>=3.12", "<=3.13,>=3.12"),
    ],
)
def test_specifier_parsing(text: str, expected: str) -> None:
    spec = PythonSpec.from_string_spec(text)
    assert spec.version_specifier == SpecifierSet.from_string(expected)


def test_specifier_with_implementation() -> None:
    spec = PythonSpec.from_string_spec("cpython>=3.12")
    assert spec.implementation == "cpython"
    assert spec.version_specifier == SpecifierSet.from_string(">=3.12")


def test_specifier_with_graalpy_implementation_alias() -> None:
    spec = PythonSpec.from_string_spec("graalvm>=3.12")
    assert spec.implementation == "graalpy"
    assert spec.version_specifier == SpecifierSet.from_string(">=3.12")


def test_specifier_satisfies_with_partial_information() -> None:
    spec = PythonSpec.from_string_spec(">=3.12")
    candidate = PythonSpec.from_string_spec("python3.12")
    assert candidate.satisfies(spec) is True


@pytest.mark.parametrize(
    ("spec_str", "expected_machine"),
    [
        pytest.param("cpython3.12-64-arm64", "arm64", id="arm64"),
        pytest.param("cpython3.12-64-x86_64", "x86_64", id="x86_64"),
        pytest.param("cpython3.12-32-x86", "x86", id="x86"),
        pytest.param("cpython3.12-64-aarch64", "arm64", id="aarch64"),
        pytest.param("cpython3.12-64-ppc64le", "ppc64le", id="ppc64le"),
        pytest.param("cpython3.12-64-s390x", "s390x", id="s390x"),
        pytest.param("cpython3.12-64-riscv64", "riscv64", id="riscv64"),
        pytest.param("cpython3.12-64", None, id="no-machine"),
        pytest.param("cpython3.12", None, id="no-arch-no-machine"),
        pytest.param("python3.12-64-arm64", "arm64", id="python-impl"),
        pytest.param("cpython3.14-64-i86pc.64bit", "i86pc.64bit", id="dotted-machine"),
    ],
)
def test_spec_parse_machine(spec_str: str, expected_machine: str | None) -> None:
    spec = PythonSpec.from_string_spec(spec_str)
    assert spec.machine == expected_machine
    assert spec.debug is None  # the debug marker sits before -arch/-machine and must not swallow the ISA


@pytest.mark.parametrize(
    ("spec_str", "expected_arch", "expected_machine"),
    [
        pytest.param("cpython3.12-64-arm64", 64, "arm64", id="64bit-arm64"),
        pytest.param("cpython3.12-32-x86", 32, "x86", id="32bit-x86"),
        pytest.param("cpython3.12-64", 64, None, id="64bit-no-machine"),
    ],
)
def test_spec_parse_arch_and_machine_together(spec_str: str, expected_arch: int, expected_machine: str | None) -> None:
    spec = PythonSpec.from_string_spec(spec_str)
    assert spec.architecture == expected_arch
    assert spec.machine == expected_machine


@pytest.mark.parametrize(
    "spec_str",
    [
        pytest.param("python3.13-dbg", id="debian-dbg"),
        pytest.param("python3.13-debug", id="debian-debug"),
        pytest.param("python3.13d", id="abi-flag"),
        pytest.param("cpython3.13d", id="impl-abi-flag"),
        pytest.param("python3.13td", id="free-threaded-debug"),
    ],
)
def test_spec_parse_debug(spec_str: str) -> None:
    spec = PythonSpec.from_string_spec(spec_str)

    assert spec.debug is True
    assert spec.major == 3
    assert spec.minor == 13
    assert spec.machine is None
    assert spec.path is None


@pytest.mark.parametrize("spec_str", ["python3.13", "python"])
def test_spec_parse_debug_unconstrained_without_marker(spec_str: str) -> None:
    assert PythonSpec.from_string_spec(spec_str).debug is None


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        pytest.param("cpython3.12-64-arm64", "cpython3.12-64-arm64", True, id="same-machine"),
        pytest.param("cpython3.12-64-arm64", "cpython3.12-64-x86_64", False, id="different-machine"),
        pytest.param("cpython3.12-64-arm64", "cpython3.12-64", True, id="none-matches-any"),
        pytest.param("cpython3.12-64-amd64", "cpython3.12-64-x86_64", True, id="amd64-eq-x86_64"),
        pytest.param("cpython3.12-64-aarch64", "cpython3.12-64-arm64", True, id="aarch64-eq-arm64"),
    ],
)
def test_spec_satisfies_machine(left: str, right: str, expected: bool) -> None:
    assert PythonSpec.from_string_spec(left).satisfies(PythonSpec.from_string_spec(right)) is expected


@pytest.mark.parametrize(
    ("isa", "normalized"),
    [
        pytest.param("amd64", "x86_64", id="amd64"),
        pytest.param("aarch64", "arm64", id="aarch64"),
        pytest.param("x86_64", "x86_64", id="x86_64"),
        pytest.param("arm64", "arm64", id="arm64"),
        pytest.param("x86", "x86", id="x86"),
        pytest.param("i386", "x86", id="i386"),
        pytest.param("i486", "x86", id="i486"),
        pytest.param("i586", "x86", id="i586"),
        pytest.param("i686", "x86", id="i686"),
        pytest.param("ppc64le", "ppc64le", id="ppc64le"),
        pytest.param("powerpc", "ppc", id="powerpc"),
        pytest.param("powerpc64", "ppc64", id="powerpc64"),
        pytest.param("powerpc64le", "ppc64le", id="powerpc64le"),
        pytest.param("riscv64", "riscv64", id="riscv64"),
        pytest.param("s390x", "s390x", id="s390x"),
        pytest.param("sparcv9", "sparc64", id="sparcv9"),
        pytest.param("sparc64", "sparc64", id="sparc64"),
        pytest.param("alpha", "alpha", id="alpha-passthrough"),
    ],
)
def test_normalize_isa(isa: str, normalized: str) -> None:
    assert normalize_isa(isa) == normalized


@pytest.mark.parametrize(
    ("spec_str", "in_repr"),
    [
        pytest.param("cpython3.12-64-arm64", "machine=arm64", id="with-machine"),
        pytest.param("cpython3.12-64", "architecture=64", id="without-machine"),
    ],
)
def test_spec_repr_machine(spec_str: str, in_repr: str) -> None:
    assert in_repr in repr(PythonSpec.from_string_spec(spec_str))


@pytest.mark.parametrize(("left", "right"), [("graalpy", "graalvm"), ("graalvm", "graalpy")])
def test_spec_satisfies_graalpy_implementation_aliases(left: str, right: str) -> None:
    spec_1 = PythonSpec.from_string_spec(left)
    spec_2 = PythonSpec.from_string_spec(right)
    assert spec_1.satisfies(spec_2) is True
