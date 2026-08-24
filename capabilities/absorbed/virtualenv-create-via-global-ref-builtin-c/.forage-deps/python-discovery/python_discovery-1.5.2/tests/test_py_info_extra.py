from __future__ import annotations

import copy
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from python_discovery import DiskCache, PythonInfo, PythonSpec
from python_discovery._py_info import VersionInfo

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

CURRENT = PythonInfo.current_system()


def test_py_info_pypy_version(mocker: MockerFixture) -> None:
    mocker.patch("platform.python_implementation", return_value="PyPy")
    mocker.patch.object(sys, "pypy_version_info", (7, 3, 11, "final", 0), create=True)
    info = PythonInfo()
    assert info.implementation == "PyPy"
    assert info.pypy_version_info == (7, 3, 11, "final", 0)


def test_py_info_canonicalizes_graalvm(mocker: MockerFixture) -> None:
    mocker.patch("platform.python_implementation", return_value="GraalVM")
    info = PythonInfo()
    assert info.implementation == "GraalPy"


def test_has_venv_attribute() -> None:
    info = PythonInfo()
    assert isinstance(info.has_venv, bool)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX only")
@pytest.mark.skipif(bool(CURRENT.sysconfig_vars.get("PYTHONFRAMEWORK")), reason="framework builds keep recorded path")
def test_from_exe_resolves_executable_only_symlink(  # pragma: no cover # skipped on framework interpreter hosts
    tmp_path: Path,
    session_cache: DiskCache,
) -> None:
    system_exe = CURRENT.system_executable
    assert system_exe is not None
    link = tmp_path / "python3"
    link.symlink_to(system_exe)
    info = PythonInfo.from_exe(str(link), session_cache, ignore_cache=True)
    assert info is not None
    assert info.system_executable is not None
    assert Path(info.system_executable).samefile(system_exe)
    assert Path(info.system_executable).parent != tmp_path


def test_version_str() -> None:
    assert CURRENT.version_str == ".".join(str(i) for i in sys.version_info[:3])


def test_version_release_str() -> None:
    assert CURRENT.version_release_str == ".".join(str(i) for i in sys.version_info[:2])


def test_python_name() -> None:
    assert CURRENT.python_name == f"python{sys.version_info.major}.{sys.version_info.minor}"


def test_is_old_virtualenv() -> None:
    info = copy.deepcopy(CURRENT)
    info.real_prefix = "/some/prefix"
    assert info.is_old_virtualenv is True
    info.real_prefix = None
    assert info.is_old_virtualenv is False


def test_is_venv() -> None:
    assert CURRENT.is_venv == (CURRENT.base_prefix is not None)


def test_system_prefix() -> None:
    info = copy.deepcopy(CURRENT)
    info.real_prefix = "/real"
    assert info.system_prefix == "/real"
    info.real_prefix = None
    info.base_prefix = "/base"
    assert info.system_prefix == "/base"


def test_system_exec_prefix() -> None:
    info = copy.deepcopy(CURRENT)
    info.real_prefix = "/real"
    assert info.system_exec_prefix == "/real"
    info.real_prefix = None
    assert info.system_exec_prefix == info.base_exec_prefix or info.exec_prefix


def test_repr() -> None:
    result = repr(CURRENT)
    assert "PythonInfo" in result


def test_str() -> None:
    result = str(CURRENT)
    assert "PythonInfo" in result
    assert "spec=" in result


def test_machine_none_platform() -> None:
    info = copy.deepcopy(CURRENT)
    info.sysconfig_platform = None
    assert info.machine == "unknown"


def test_from_json_round_trip() -> None:
    json_str = CURRENT.to_json()
    restored = PythonInfo.from_json(json_str)
    assert restored.version_info == CURRENT.version_info
    assert restored.implementation == CURRENT.implementation


def test_from_dict() -> None:
    data = CURRENT.to_dict()
    restored = PythonInfo.from_dict(data)
    assert restored.version_info == CURRENT.version_info


def test_resolve_to_system_circle(mocker: MockerFixture, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    target = copy.deepcopy(CURRENT)
    target.system_executable = None
    target.real_prefix = None
    target.base_prefix = "/prefix_a"

    second = copy.deepcopy(CURRENT)
    second.system_executable = None
    second.real_prefix = None
    second.base_prefix = "/prefix_b"

    third = copy.deepcopy(CURRENT)
    third.system_executable = None
    third.real_prefix = None
    third.base_prefix = "/prefix_a"

    mocker.patch.object(PythonInfo, "discover_exe", side_effect=[second, third])

    with pytest.raises(RuntimeError, match="prefixes are causing a circle"):
        PythonInfo.resolve_to_system(None, target)


def test_resolve_to_system_single_prefix_self_link(mocker: MockerFixture, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    target = copy.deepcopy(CURRENT)
    target.system_executable = None
    target.real_prefix = None
    target.base_prefix = "/prefix_a"

    second = copy.deepcopy(CURRENT)
    second.system_executable = None
    second.real_prefix = None
    second.base_prefix = "/prefix_a"

    mocker.patch.object(PythonInfo, "discover_exe", return_value=second)

    result = PythonInfo.resolve_to_system(None, target)
    assert result.system_executable is not None
    assert any("links back to itself" in r.message for r in caplog.records)


def test_discover_exe_cache_hit() -> None:
    info = copy.deepcopy(CURRENT)
    cached = copy.deepcopy(CURRENT)
    PythonInfo._cache_exe_discovery["/some/prefix", True] = cached
    try:
        result = info.discover_exe(MagicMock(), prefix="/some/prefix", exact=True)
        assert result is cached
    finally:
        del PythonInfo._cache_exe_discovery["/some/prefix", True]


def test_check_exe_none_path(tmp_path: Path) -> None:
    info = copy.deepcopy(CURRENT)
    result = info._check_exe(MagicMock(), str(tmp_path), "nonexistent", [], dict(os.environ), exact=True)
    assert result is None


def test_satisfies_version_specifier() -> None:
    spec = PythonSpec.from_string_spec(f">={sys.version_info.major}.{sys.version_info.minor}")
    assert CURRENT.satisfies(spec, impl_must_match=False) is True


def test_satisfies_version_specifier_fails() -> None:
    spec = PythonSpec.from_string_spec(f">{sys.version_info.major + 1}")
    assert CURRENT.satisfies(spec, impl_must_match=False) is False


@pytest.mark.parametrize(
    ("version_info", "spec_str", "expected"),
    [
        pytest.param(VersionInfo(3, 14, 0, "alpha", 1), ">=3.14.0a1", True, id="alpha_match_exact"),
        pytest.param(VersionInfo(3, 14, 0, "beta", 1), ">=3.14.0b1", True, id="beta_match_exact"),
        pytest.param(VersionInfo(3, 14, 0, "candidate", 1), ">=3.14.0rc1", True, id="rc_match_exact"),
        pytest.param(VersionInfo(3, 15, 0, "alpha", 6), ">=3.15", True, id="prerelease_match_major_minor"),
        pytest.param(VersionInfo(3, 15, 0, "alpha", 6), ">=3.15.0", False, id="prerelease_not_match_full_precision"),
        pytest.param(VersionInfo(3, 15, 0, "alpha", 5), "<3.15.0a6", True, id="earlier_prerelease_less_than"),
        pytest.param(VersionInfo(3, 15, 0, "alpha", 6), "<3.15.0a6", False, id="prerelease_not_less_than_itself"),
        pytest.param(VersionInfo(3, 15, 0, "alpha", 6), ">=3.15.0a6", True, id="prerelease_match_itself"),
        pytest.param(VersionInfo(3, 15, 0, "alpha", 6), ">=3.15.0a7", False, id="prerelease_not_match_later"),
        pytest.param(VersionInfo(3, 15, 0, "final", 0), ">=3.15.0a6", True, id="final_greater_than_prerelease"),
        pytest.param(VersionInfo(3, 15, 0, "final", 0), "<3.15.0a6", False, id="final_not_less_than_prerelease"),
        pytest.param(VersionInfo(3, 15, 0, "final", 0), ">=3.15", True, id="final_match_major_minor"),
        pytest.param(VersionInfo(3, 15, 1, "alpha", 1), ">=3.15.0", True, id="later_micro_prerelease_match"),
    ],
)
def test_satisfies_version_specifier_prerelease(version_info: VersionInfo, spec_str: str, expected: bool) -> None:
    info = copy.deepcopy(CURRENT)
    info.version_info = version_info
    spec = PythonSpec.from_string_spec(spec_str)
    assert info.satisfies(spec, impl_must_match=False) is expected


def test_satisfies_path_not_abs_basename_match() -> None:
    info = copy.deepcopy(CURRENT)
    # stem drops everything from the first dot, so python3.15t arrives as python3 and stops naming a free-threaded
    # build; only the Windows .exe belongs off the end.
    name = Path(info.original_executable).name
    basename = name[: -len(".exe")] if name.endswith(".exe") else name
    spec = PythonSpec.from_string_spec(basename)
    assert info.satisfies(spec, impl_must_match=False) is True


def test_satisfies_path_not_abs_basename_no_match() -> None:
    info = copy.deepcopy(CURRENT)
    spec = PythonSpec.from_string_spec("completely_different_name")
    assert info.satisfies(spec, impl_must_match=False) is False


@pytest.mark.skipif(sys.platform == "win32", reason="win32 tested separately")
def test_satisfies_path_win32(mocker: MockerFixture) -> None:
    info = copy.deepcopy(CURRENT)
    mocker.patch.object(sys, "platform", "win32")
    info.original_executable = "/some/path/python.exe"
    spec = PythonSpec.from_string_spec("python")
    spec.path = "python"
    assert info.satisfies(spec, impl_must_match=False) is True


def test_install_path() -> None:
    assert isinstance(CURRENT.install_path("purelib"), str)


def test_system_include() -> None:
    result = CURRENT.system_include
    assert isinstance(result, str)


def test_system_include_fallback(mocker: MockerFixture) -> None:
    info = copy.deepcopy(CURRENT)
    mocker.patch("os.path.exists", side_effect=lambda p: "include" not in p or "dist" in p.lower())
    result = info.system_include
    assert isinstance(result, str)


def test_sysconfig_path_missing_key() -> None:
    assert not CURRENT.sysconfig_path("nonexistent_key")


def test_sysconfig_path_with_config_var() -> None:
    result = CURRENT.sysconfig_path("stdlib", {})
    assert isinstance(result, str)


def test_current_system_cached(session_cache: DiskCache) -> None:
    PythonInfo._current_system = None
    result1 = PythonInfo.current_system(session_cache)
    result2 = PythonInfo.current_system(session_cache)
    assert result1 is result2


def test_current_cached(session_cache: DiskCache) -> None:
    PythonInfo._current = None
    result1 = PythonInfo.current(session_cache)
    result2 = PythonInfo.current(session_cache)
    assert result1 is result2


def test_from_exe_resolve_error(mocker: MockerFixture, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    fake_info = PythonInfo()
    fake_info.original_executable = "/fake/python"
    mocker.patch(
        "python_discovery._cached_py_info.from_exe",
        return_value=fake_info,
    )
    mocker.patch.object(PythonInfo, "resolve_to_system", side_effect=RuntimeError("test error"))
    result = PythonInfo.from_exe(sys.executable, raise_on_error=False, resolve_to_host=True)
    assert result is None
    assert any("cannot resolve system" in r.message for r in caplog.records)


def test_sysconfig_path_no_config_var() -> None:
    result = CURRENT.sysconfig_path("stdlib")
    assert isinstance(result, str)
    assert len(result) > 0


def test_satisfies_abs_spec_path_falls_through() -> None:
    info = copy.deepcopy(CURRENT)
    spec = PythonSpec("", None, None, None, None, None, "/some/other/python")
    assert spec.is_abs is True
    assert info.satisfies(spec, impl_must_match=False) is True


def test_satisfies_abs_spec_path_match() -> None:
    info = copy.deepcopy(CURRENT)
    spec = PythonSpec("", None, None, None, None, None, info.executable)
    assert info.satisfies(spec, impl_must_match=False) is True


def test_current_returns_none_raises(mocker: MockerFixture) -> None:
    PythonInfo._current = None
    mocker.patch.object(PythonInfo, "from_exe", return_value=None)
    with pytest.raises(RuntimeError, match="failed to query current Python interpreter"):
        PythonInfo.current()
    PythonInfo._current = None


def test_current_system_returns_none_raises(mocker: MockerFixture) -> None:
    PythonInfo._current_system = None
    mocker.patch.object(PythonInfo, "from_exe", return_value=None)
    with pytest.raises(RuntimeError, match="failed to query current system Python interpreter"):
        PythonInfo.current_system()
    PythonInfo._current_system = None


def test_check_exe_from_exe_returns_none(tmp_path: Path, mocker: MockerFixture) -> None:
    info = copy.deepcopy(CURRENT)
    exe = tmp_path / "python"
    exe.touch()
    mocker.patch.object(PythonInfo, "from_exe", return_value=None)
    result = info._check_exe(MagicMock(), str(tmp_path), "python", [], dict(os.environ), exact=True)
    assert result is None


def test_check_exe_mismatch_not_exact(tmp_path: Path, mocker: MockerFixture) -> None:
    info = copy.deepcopy(CURRENT)
    exe = tmp_path / "python"
    exe.touch()
    other = copy.deepcopy(CURRENT)
    other.architecture = 32 if info.architecture == 64 else 64
    mocker.patch.object(PythonInfo, "from_exe", return_value=other)
    discovered: list[PythonInfo] = []
    result = info._check_exe(MagicMock(), str(tmp_path), "python", discovered, dict(os.environ), exact=False)
    assert result is None
    assert len(discovered) == 1


def test_check_exe_mismatch_exact(tmp_path: Path, mocker: MockerFixture) -> None:
    info = copy.deepcopy(CURRENT)
    exe = tmp_path / "python"
    exe.touch()
    other = copy.deepcopy(CURRENT)
    other.architecture = 32 if info.architecture == 64 else 64
    mocker.patch.object(PythonInfo, "from_exe", return_value=other)
    discovered: list[PythonInfo] = []
    result = info._check_exe(MagicMock(), str(tmp_path), "python", discovered, dict(os.environ), exact=True)
    assert result is None
    assert len(discovered) == 0


def test_find_possible_exe_names_free_threaded() -> None:
    info = copy.deepcopy(CURRENT)
    info.free_threaded = True
    names = info._find_possible_exe_names()
    assert any("t" in n for n in names)


def test_possible_base_python_basename() -> None:
    info = copy.deepcopy(CURRENT)
    info.executable = "/usr/bin/python"
    info.implementation = "CPython"
    names = list(info._possible_base())
    assert "python" in names
    assert "cpython" in names


def test_possible_base_case_sensitive(mocker: MockerFixture) -> None:
    info = copy.deepcopy(CURRENT)
    info.executable = "/usr/bin/CPython3.12"
    info.implementation = "CPython"
    mocker.patch("python_discovery._compat.fs_is_case_sensitive", return_value=True)
    names = list(info._possible_base())
    lower_names = [n for n in names if n.islower()]
    upper_names = [n for n in names if n.isupper()]
    assert len(lower_names) >= 1
    assert len(upper_names) >= 1


def test_possible_base_case_sensitive_upper_equals_base(mocker: MockerFixture) -> None:
    info = copy.deepcopy(CURRENT)
    info.executable = "/usr/bin/JYTHON"
    info.implementation = "JYTHON"
    mocker.patch("python_discovery._compat.fs_is_case_sensitive", return_value=True)
    names = list(info._possible_base())
    assert "jython" in names
    assert "JYTHON" in names


def test_resolve_to_system_resolved_from_exe(mocker: MockerFixture, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    target = copy.deepcopy(CURRENT)
    target.system_executable = "/some/system/python"
    target.executable = "/some/venv/python"

    resolved = copy.deepcopy(CURRENT)
    resolved.system_executable = "/some/system/python"
    resolved.executable = "/some/system/python"

    mocker.patch.object(PythonInfo, "from_exe", return_value=resolved)
    result = PythonInfo.resolve_to_system(None, target)
    assert result.executable == "/some/venv/python"


def test_resolve_to_system_from_exe_returns_none(mocker: MockerFixture) -> None:
    target = copy.deepcopy(CURRENT)
    target.system_executable = "/some/system/python"
    target.executable = "/some/venv/python"

    mocker.patch.object(PythonInfo, "from_exe", return_value=None)
    result = PythonInfo.resolve_to_system(None, target)
    assert result.executable == "/some/venv/python"
