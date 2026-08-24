from __future__ import annotations

import copy
import itertools
import json
import logging
import os
import sys
import sysconfig
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING, NamedTuple

import pytest
from setuptools.dist import Distribution

from python_discovery import DiskCache, PythonInfo, PythonSpec
from python_discovery import _cached_py_info as cached_py_info
from python_discovery._py_info import VersionInfo

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

IS_PYPY = PythonInfo.current_system().implementation == "PyPy"

CURRENT = PythonInfo.current_system()


@pytest.mark.graalpy
def test_current_as_json() -> None:
    result = CURRENT.to_json()
    parsed = json.loads(result)
    major, minor, micro, releaselevel, serial = sys.version_info
    free_threaded = sysconfig.get_config_var("Py_GIL_DISABLED") == 1
    assert parsed["version_info"] == {
        "major": major,
        "minor": minor,
        "micro": micro,
        "releaselevel": releaselevel,
        "serial": serial,
    }
    assert parsed["free_threaded"] is free_threaded
    assert parsed["debug_build"] is bool(sysconfig.get_config_var("Py_DEBUG"))


def test_bad_exe_py_info_raise(tmp_path: Path, session_cache: DiskCache) -> None:
    exe = str(tmp_path)
    with pytest.raises(RuntimeError) as context:
        PythonInfo.from_exe(exe, session_cache)
    msg = str(context.value)
    assert "code" in msg
    assert exe in msg


def test_bad_exe_py_info_no_raise(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
    session_cache: DiskCache,
) -> None:
    caplog.set_level(logging.NOTSET)
    exe = str(tmp_path)
    result = PythonInfo.from_exe(exe, session_cache, raise_on_error=False)
    assert result is None
    out, _ = capsys.readouterr()
    assert not out
    messages = [r.message for r in caplog.records if r.name != "filelock"]
    assert len(messages) == 4
    assert "get interpreter info via cmd: " in messages[0]
    assert "retrying" in messages[1]
    assert "get interpreter info via cmd: " in messages[2]
    assert str(exe) in messages[3]
    assert "code" in messages[3]


@pytest.mark.parametrize(
    "spec",
    itertools.chain(
        [sys.executable],
        [
            f"{impl}{'.'.join(str(i) for i in ver)}{'t' if CURRENT.free_threaded else ''}{arch}"
            for impl, ver, arch in itertools.product(
                (
                    [CURRENT.implementation]
                    + (["python"] if CURRENT.implementation == "CPython" else [])
                    + (
                        [CURRENT.implementation.lower()]
                        if CURRENT.implementation != CURRENT.implementation.lower()
                        else []
                    )
                ),
                [sys.version_info[0 : i + 1] for i in range(3)],
                ["", f"-{CURRENT.architecture}"],
            )
        ],
    ),
)
def test_satisfy_py_info(spec: str) -> None:
    parsed_spec = PythonSpec.from_string_spec(spec)
    matches = CURRENT.satisfies(parsed_spec, impl_must_match=True)
    assert matches is True


def test_satisfy_not_arch() -> None:
    parsed_spec = PythonSpec.from_string_spec(
        f"{CURRENT.implementation}-{64 if CURRENT.architecture == 32 else 32}",
    )
    matches = CURRENT.satisfies(parsed_spec, impl_must_match=True)
    assert matches is False


def test_satisfy_not_threaded() -> None:
    parsed_spec = PythonSpec.from_string_spec(
        f"{CURRENT.implementation}{CURRENT.version_info.major}{'' if CURRENT.free_threaded else 't'}",
    )
    matches = CURRENT.satisfies(parsed_spec, impl_must_match=True)
    assert matches is False


def _generate_not_match_current_interpreter_version() -> list[str]:
    result: list[str] = []
    for depth in range(3):
        ver: list[int] = [int(part) for part in sys.version_info[0 : depth + 1]]
        for idx in range(len(ver)):
            for offset in [-1, 1]:
                temp = ver.copy()
                temp[idx] += offset
                result.append(".".join(str(part) for part in temp))
    return result


_NON_MATCH_VER = _generate_not_match_current_interpreter_version()


@pytest.mark.parametrize("spec", _NON_MATCH_VER)
def test_satisfy_not_version(spec: str) -> None:
    parsed_spec = PythonSpec.from_string_spec(f"{CURRENT.implementation}{spec}")
    matches = CURRENT.satisfies(parsed_spec, impl_must_match=True)
    assert matches is False


def test_py_info_cached_error(mocker: MockerFixture, tmp_path: Path, session_cache: DiskCache) -> None:
    spy = mocker.spy(cached_py_info, "_run_subprocess")
    with pytest.raises(RuntimeError):
        PythonInfo.from_exe(str(tmp_path), session_cache)
    with pytest.raises(RuntimeError):
        PythonInfo.from_exe(str(tmp_path), session_cache)
    assert spy.call_count == 2


def test_py_info_cache_clear(mocker: MockerFixture, session_cache: DiskCache) -> None:
    result = PythonInfo.from_exe(sys.executable, session_cache)
    assert result is not None

    PythonInfo.clear_cache(session_cache)
    assert not cached_py_info._CACHE

    spy = mocker.spy(cached_py_info, "_run_subprocess")
    info = PythonInfo.from_exe(sys.executable, session_cache)
    assert info is not None

    native_difference = 1 if info.system_executable == info.executable else 0
    assert spy.call_count + native_difference >= 1


class PyInfoMock(NamedTuple):
    implementation: str
    architecture: int
    version_info: VersionInfo


@pytest.mark.parametrize(
    ("target", "position", "discovered"),
    [
        (
            PyInfoMock("CPython", 64, VersionInfo(3, 6, 8, "final", 0)),
            0,
            [
                PyInfoMock("CPython", 64, VersionInfo(3, 6, 9, "final", 0)),
                PyInfoMock("PyPy", 64, VersionInfo(3, 6, 8, "final", 0)),
            ],
        ),
        (
            PyInfoMock("CPython", 64, VersionInfo(3, 6, 8, "final", 0)),
            0,
            [
                PyInfoMock("CPython", 64, VersionInfo(3, 6, 9, "final", 0)),
                PyInfoMock("CPython", 32, VersionInfo(3, 6, 9, "final", 0)),
            ],
        ),
        (
            PyInfoMock("CPython", 64, VersionInfo(3, 8, 1, "final", 0)),
            0,
            [
                PyInfoMock("CPython", 32, VersionInfo(2, 7, 12, "rc", 2)),
                PyInfoMock("PyPy", 64, VersionInfo(3, 8, 1, "final", 0)),
            ],
        ),
    ],
)
def test_system_executable_no_exact_match(
    target: PyInfoMock,
    discovered: list[PyInfoMock],
    position: int,
    *,
    tmp_path: Path,
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
    session_cache: DiskCache,
) -> None:
    caplog.set_level(logging.DEBUG)

    def _make_py_info(of: PyInfoMock) -> PythonInfo:
        base = copy.deepcopy(CURRENT)
        base.implementation = of.implementation
        base.version_info = of.version_info
        base.architecture = of.architecture
        return base

    discovered_with_path: dict[str, PythonInfo] = {}
    names: list[str] = []
    selected = None
    for pos, i in enumerate(discovered):
        path = tmp_path / str(pos)
        path.write_text("", encoding="utf-8")
        py_info = _make_py_info(i)
        system_executable = CURRENT.system_executable
        assert system_executable is not None
        py_info.system_executable = system_executable
        py_info.executable = system_executable
        py_info.base_executable = str(path)  # ty: ignore[unresolved-attribute]
        if pos == position:
            selected = py_info
        discovered_with_path[str(path)] = py_info
        names.append(path.name)

    target_py_info = _make_py_info(target)
    mocker.patch.object(target_py_info, "_find_possible_exe_names", return_value=names)
    mocker.patch.object(target_py_info, "_find_possible_folders", return_value=[str(tmp_path)])

    def func(exe_path: str, _cache: object = None, **_kwargs: object) -> PythonInfo:
        return discovered_with_path[exe_path]

    mocker.patch.object(target_py_info, "from_exe", side_effect=func)
    target_py_info.real_prefix = str(tmp_path)

    target_py_info.system_executable = None
    target_py_info.executable = str(tmp_path)
    mapped = target_py_info.resolve_to_system(session_cache, target_py_info)
    assert mapped.system_executable == CURRENT.system_executable
    found = discovered_with_path[mapped.base_executable]
    assert found is selected

    assert caplog.records[0].msg == "discover exe for %s in %s"
    for record in caplog.records[1:-1]:
        assert record.message.startswith("refused interpreter ")
        assert record.levelno == logging.DEBUG

    warn_similar = caplog.records[-1]
    assert warn_similar.levelno == logging.DEBUG
    assert warn_similar.msg.startswith("no exact match found, chosen most similar")


@pytest.mark.parametrize("attr", ["free_threaded", "debug_build"])
def test_discover_exe_validates_abi_flag(
    attr: str, tmp_path: Path, mocker: MockerFixture, session_cache: DiskCache
) -> None:
    def candidate(*, flag: bool, name: str) -> PythonInfo:
        info = copy.deepcopy(CURRENT)
        setattr(info, attr, flag)
        exe = tmp_path / name
        exe.write_text("", encoding="utf-8")
        info.executable = str(exe)
        return info

    target = candidate(flag=True, name="target")
    mismatch = candidate(flag=False, name="release")
    match = candidate(flag=True, name="debug")
    by_path = {info.executable: info for info in (mismatch, match)}

    mocker.patch.object(target, "_find_possible_exe_names", return_value=["release", "debug"])
    mocker.patch.object(target, "_find_possible_folders", return_value=[str(tmp_path)])
    mocker.patch.object(target, "from_exe", side_effect=lambda exe, *_a, **_k: by_path[exe])

    found = target.discover_exe(session_cache, prefix=str(tmp_path), exact=True)
    assert found is match  # the release build is refused even though version, impl and arch match


def test_py_info_ignores_distutils_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    raw = f"""
    [install]
    prefix={tmp_path}{os.sep}prefix
    install_purelib={tmp_path}{os.sep}purelib
    install_platlib={tmp_path}{os.sep}platlib
    install_headers={tmp_path}{os.sep}headers
    install_scripts={tmp_path}{os.sep}scripts
    install_data={tmp_path}{os.sep}data
    """
    (tmp_path / "setup.cfg").write_text(dedent(raw), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    py_info = PythonInfo.from_exe(sys.executable)
    assert py_info is not None
    distutils = py_info.distutils_install
    for key, value in distutils.items():  # pragma: no cover # distutils_install is empty with "venv" scheme
        assert not value.startswith(str(tmp_path)), f"{key}={value}"


def test_discover_exe_on_path_non_spec_name_match(mocker: MockerFixture) -> None:
    suffixed_name = f"python{CURRENT.version_info.major}.{CURRENT.version_info.minor}m"
    if sys.platform == "win32":  # pragma: win32 cover
        suffixed_name += Path(CURRENT.original_executable).suffix
    spec = PythonSpec.from_string_spec(suffixed_name)
    mocker.patch.object(CURRENT, "original_executable", str(Path(CURRENT.executable).parent / suffixed_name))
    assert CURRENT.satisfies(spec, impl_must_match=True) is True


def test_satisfies_debug_spec_requires_debug_build(mocker: MockerFixture) -> None:
    spec = PythonSpec.from_string_spec(f"python{CURRENT.version_info.major}.{CURRENT.version_info.minor}-dbg")
    assert spec.debug is True
    mocker.patch.object(CURRENT, "free_threaded", spec.free_threaded)

    mocker.patch.object(CURRENT, "debug_build", False)
    assert CURRENT.satisfies(spec, impl_must_match=True) is False

    mocker.patch.object(CURRENT, "debug_build", True)
    assert CURRENT.satisfies(spec, impl_must_match=True) is True


def test_discover_exe_on_path_non_spec_name_not_match(mocker: MockerFixture) -> None:
    suffixed_name = f"python{CURRENT.version_info.major}.{CURRENT.version_info.minor}m"
    if sys.platform == "win32":  # pragma: win32 cover
        suffixed_name += Path(CURRENT.original_executable).suffix
    spec = PythonSpec.from_string_spec(suffixed_name)
    mocker.patch.object(
        CURRENT,
        "original_executable",
        str(Path(CURRENT.executable).parent / f"e{suffixed_name}"),
    )
    assert CURRENT.satisfies(spec, impl_must_match=True) is False


@pytest.mark.skipif(IS_PYPY, reason="setuptools distutils patching does not work")
def test_py_info_setuptools() -> None:
    assert Distribution
    PythonInfo()


@pytest.mark.usefixtures("_skip_if_test_in_system")
def test_py_info_to_system_raises(  # pragma: no cover # skipped in venv environments
    session_cache: DiskCache,
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    mocker.patch.object(PythonInfo, "_find_possible_folders", return_value=[])
    result = PythonInfo.from_exe(sys.executable, cache=session_cache, raise_on_error=False)
    assert result is None
    log = caplog.records[-1]
    assert log.levelno == logging.INFO
    expected = f"ignore {sys.executable} due cannot resolve system due to RuntimeError('failed to detect "
    assert expected in log.message


def test_sysconfig_vars_include_shared_lib_keys() -> None:
    for key in ("Py_ENABLE_SHARED", "INSTSONAME", "LIBDIR"):
        assert key in CURRENT.sysconfig_vars


def test_py_info_has_sysconfig_platform() -> None:
    assert hasattr(CURRENT, "sysconfig_platform")
    assert CURRENT.sysconfig_platform is not None
    assert isinstance(CURRENT.sysconfig_platform, str)
    assert len(CURRENT.sysconfig_platform) > 0


def test_py_info_machine_property() -> None:
    machine = CURRENT.machine
    assert machine is not None
    assert isinstance(machine, str)
    assert len(machine) > 0
    assert machine == machine.lower(), f"machine value should be lowercase: {machine}"


def test_py_info_machine_in_spec() -> None:
    spec = CURRENT.spec
    assert CURRENT.machine in spec
    assert f"-{CURRENT.architecture}-{CURRENT.machine}" in spec


def test_py_info_sysconfig_platform_matches_sysconfig() -> None:
    assert CURRENT.sysconfig_platform == sysconfig.get_platform()


@pytest.mark.parametrize(
    ("platform", "expected"),
    [
        pytest.param("win32", "x86", id="win32"),
        pytest.param("win-amd64", "x86_64", id="win-amd64"),
        pytest.param("win-arm64", "arm64", id="win-arm64"),
        pytest.param("linux-x86_64", "x86_64", id="linux-x86_64"),
        pytest.param("linux-aarch64", "arm64", id="linux-aarch64"),
        pytest.param("linux-riscv64", "riscv64", id="linux-riscv64"),
        pytest.param("linux-ppc64le", "ppc64le", id="linux-ppc64le"),
        pytest.param("linux-s390x", "s390x", id="linux-s390x"),
        pytest.param("macosx-14.0-arm64", "arm64", id="macos-arm64"),
        pytest.param("macosx-14.0-x86_64", "x86_64", id="macos-x86_64"),
    ],
)
def test_py_info_machine_derivation(platform: str, expected: str) -> None:
    info = copy.deepcopy(CURRENT)
    info.sysconfig_platform = platform
    assert info.machine == expected


@pytest.mark.parametrize("runtime_isa", ["arm64", "x86_64"])
def test_py_info_machine_derivation_universal2(mocker: MockerFixture, runtime_isa: str) -> None:
    info = copy.deepcopy(CURRENT)
    info.sysconfig_platform = "macosx-11.0-universal2"
    mocker.patch("python_discovery._py_info.platform.machine", return_value=runtime_isa)
    assert info.machine == runtime_isa


def test_py_info_satisfies_with_machine() -> None:
    threaded = "t" if CURRENT.free_threaded else ""
    spec_str = (
        f"{CURRENT.implementation}{CURRENT.version_info.major}{threaded}-{CURRENT.architecture}-{CURRENT.machine}"
    )
    parsed_spec = PythonSpec.from_string_spec(spec_str)
    assert CURRENT.satisfies(parsed_spec, impl_must_match=True) is True


def test_py_info_satisfies_not_machine() -> None:
    other_machine = "arm64" if CURRENT.machine != "arm64" else "x86_64"
    spec_str = f"{CURRENT.implementation}-{CURRENT.architecture}-{other_machine}"
    parsed_spec = PythonSpec.from_string_spec(spec_str)
    assert CURRENT.satisfies(parsed_spec, impl_must_match=True) is False


def test_py_info_satisfies_no_machine_in_spec() -> None:
    threaded = "t" if CURRENT.free_threaded else ""
    spec_str = f"{CURRENT.implementation}{CURRENT.version_info.major}{threaded}-{CURRENT.architecture}"
    parsed_spec = PythonSpec.from_string_spec(spec_str)
    assert parsed_spec.machine is None
    assert CURRENT.satisfies(parsed_spec, impl_must_match=True) is True


@pytest.mark.parametrize(
    ("platform", "spec_machine"),
    [
        pytest.param("linux-x86_64", "amd64", id="amd64-matches-x86_64"),
        pytest.param("macosx-14.0-arm64", "aarch64", id="aarch64-matches-arm64"),
    ],
)
def test_py_info_satisfies_machine_cross_os_normalization(platform: str, spec_machine: str) -> None:
    info = copy.deepcopy(CURRENT)
    info.sysconfig_platform = platform
    spec = PythonSpec.from_string_spec(f"{info.implementation}-{info.architecture}-{spec_machine}")
    assert info.satisfies(spec, impl_must_match=True) is True


@pytest.mark.parametrize("debug", [True, False], ids=["debug", "release"])
def test_py_info_debug_build_in_spec(*, debug: bool) -> None:
    info = copy.deepcopy(CURRENT)
    info.debug_build = debug
    assert ("d-" in info.spec) is debug


@pytest.mark.parametrize("debug", [True, False], ids=["debug", "release"])
def test_py_info_debug_build_exe_names(*, debug: bool) -> None:
    info = copy.deepcopy(CURRENT)
    info.debug_build = debug
    names = info._find_possible_exe_names()
    abiflag_name = f"python{info.version_info.major}.{info.version_info.minor}d"
    assert any("_d" in n for n in names) is debug
    assert any(n.endswith("-dbg") for n in names) is debug
    assert (abiflag_name in names) is debug


def test_py_info_debug_build_json_round_trip() -> None:
    info = copy.deepcopy(CURRENT)
    info.debug_build = True
    restored = PythonInfo.from_json(info.to_json())
    assert restored.debug_build is True


def test_py_info_to_dict_includes_sysconfig_platform() -> None:
    data = CURRENT.to_dict()
    assert "sysconfig_platform" in data
    assert data["sysconfig_platform"] == sysconfig.get_platform()


def test_py_info_json_round_trip() -> None:
    json_str = CURRENT.to_json()
    parsed = json.loads(json_str)
    assert "sysconfig_platform" in parsed
    restored = PythonInfo.from_json(json_str)
    assert restored.sysconfig_platform == CURRENT.sysconfig_platform
    assert restored.machine == CURRENT.machine


@pytest.mark.parametrize(
    ("target_platform", "discovered_platforms", "expected_idx"),
    [
        pytest.param("linux-x86_64", ["linux-aarch64", "linux-x86_64"], 1, id="x86_64-over-aarch64"),
        pytest.param("macosx-14.0-arm64", ["macosx-14.0-x86_64", "macosx-14.0-arm64"], 1, id="arm64-over-x86_64"),
    ],
)
def test_select_most_likely_prefers_machine_match(
    target_platform: str,
    discovered_platforms: list[str],
    expected_idx: int,
) -> None:
    target = copy.deepcopy(CURRENT)
    target.sysconfig_platform = target_platform
    discovered = [copy.deepcopy(CURRENT) for _ in discovered_platforms]
    for d, plat in zip(discovered, discovered_platforms):
        d.sysconfig_platform = plat
    result = PythonInfo._select_most_likely(discovered, target)
    assert result.sysconfig_platform == discovered_platforms[expected_idx]
