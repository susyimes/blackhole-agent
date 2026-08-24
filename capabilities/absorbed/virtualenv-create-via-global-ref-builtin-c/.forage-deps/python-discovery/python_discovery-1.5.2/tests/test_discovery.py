from __future__ import annotations

import logging
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final
from unittest.mock import patch
from uuid import uuid4

import pytest

from python_discovery import DiskCache, PythonInfo, get_interpreter
from python_discovery._discovery import IS_WIN, LazyPathDump, get_paths

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytest_mock import MockerFixture


@pytest.mark.graalpy
@pytest.mark.skipif(not Path(sys.executable).is_symlink() and not Path(sys.executable).is_file(), reason="no symlink")
@pytest.mark.parametrize("case", ["mixed", "lower", "upper"])
@pytest.mark.parametrize("specificity", ["more", "less", "none"])
def test_discovery_via_path(
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    specificity: str,
    *,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    session_cache: DiskCache,
) -> None:
    caplog.set_level(logging.DEBUG)
    current = PythonInfo.current_system(session_cache)
    name = "somethingVeryCryptic"
    threaded = "t" if current.free_threaded else ""
    if case == "lower":
        name = name.lower()
    elif case == "upper":
        name = name.upper()
    if specificity == "more":
        core_ver = current.version_info.major
        exe_ver = ".".join(str(i) for i in current.version_info[0:2]) + threaded
    elif specificity == "less":
        core_ver = ".".join(str(i) for i in current.version_info[0:3])
        exe_ver = current.version_info.major
    elif specificity == "none":  # pragma: no branch
        core_ver = ".".join(str(i) for i in current.version_info[0:3])
        exe_ver = ""
    core = "" if specificity == "none" else f"{name}{core_ver}{threaded}"
    exe_name = f"{name}{exe_ver}{'.exe' if sys.platform == 'win32' else ''}"
    target = tmp_path / current.install_path("scripts")
    target.mkdir(parents=True)
    executable = target / exe_name
    Path(str(executable)).symlink_to(sys.executable)
    pyvenv_cfg = Path(sys.executable).parents[1] / "pyvenv.cfg"
    if pyvenv_cfg.exists():  # pragma: no branch
        (target / pyvenv_cfg.name).write_bytes(pyvenv_cfg.read_bytes())
    new_path = os.pathsep.join([str(target), *os.environ.get("PATH", "").split(os.pathsep)])
    monkeypatch.setenv("PATH", new_path)
    interpreter = get_interpreter(core, [])

    assert interpreter is not None


def test_discovery_via_path_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    interpreter = get_interpreter(uuid4().hex, [])
    assert interpreter is None


def test_discovery_via_path_in_nonbrowseable_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bad_perm = tmp_path / "bad_perm"
    bad_perm.mkdir(mode=0o000)
    monkeypatch.setenv("PATH", str(bad_perm))
    interpreter = get_interpreter(uuid4().hex, [])
    assert interpreter is None
    monkeypatch.setenv("PATH", str(bad_perm / "bin"))
    interpreter = get_interpreter(uuid4().hex, [])
    assert interpreter is None


def test_relative_path(session_cache: DiskCache, monkeypatch: pytest.MonkeyPatch) -> None:
    sys_executable = Path(PythonInfo.current_system(session_cache).system_executable)
    cwd = sys_executable.parents[1]
    monkeypatch.chdir(str(cwd))
    relative = str(sys_executable.relative_to(cwd))
    result = get_interpreter(relative, [], session_cache)
    assert result is not None


def test_discovery_fallback_fail(session_cache: DiskCache, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    result = get_interpreter(["magic-one", "magic-two"], cache=session_cache)
    assert result is None
    assert "accepted" not in caplog.text


def test_discovery_fallback_ok(session_cache: DiskCache, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    result = get_interpreter(["magic-one", sys.executable], cache=session_cache)
    assert result is not None, caplog.text
    assert result.executable == sys.executable, caplog.text
    assert "accepted" in caplog.text


@pytest.fixture
def mock_find_interpreter(mocker: MockerFixture) -> None:
    mocker.patch(
        "python_discovery._discovery._find_interpreter",
        lambda key, *_args, **_kwargs: getattr(mocker.sentinel, key),
    )


@pytest.mark.usefixtures("mock_find_interpreter")
def test_returns_first_python_specified(mocker: MockerFixture) -> None:
    result = get_interpreter(["python_from_cli"])
    assert result == mocker.sentinel.python_from_cli


def test_discovery_absolute_path_with_try_first(
    tmp_path: Path,
    session_cache: DiskCache,
) -> None:
    good_env = tmp_path / "good"
    bad_env = tmp_path / "bad"

    subprocess.check_call([sys.executable, "-m", "venv", str(good_env)])
    subprocess.check_call([sys.executable, "-m", "venv", str(bad_env)])

    scripts_dir = "Scripts" if IS_WIN else "bin"
    exe_name = "python.exe" if IS_WIN else "python"
    good_exe = good_env / scripts_dir / exe_name
    bad_exe = bad_env / scripts_dir / exe_name

    interpreter = get_interpreter(
        str(good_exe),
        try_first_with=[str(bad_exe)],
        cache=session_cache,
    )

    assert interpreter is not None
    assert Path(interpreter.executable) == good_exe


def test_discovery_via_path_with_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    a_file = tmp_path / "a_file"
    a_file.touch()
    monkeypatch.setenv("PATH", str(a_file))
    interpreter = get_interpreter(uuid4().hex, [])
    assert interpreter is None


def test_get_paths_no_path_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PATH", raising=False)
    paths = list(get_paths({}))
    assert paths


def test_lazy_path_dump_debug(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("_VIRTUALENV_DEBUG", "1")
    a_dir = tmp_path
    executable_file = "a_file.exe" if IS_WIN else "a_file"
    (a_dir / executable_file).touch(mode=0o755)
    (a_dir / "b_file").touch(mode=0o644)
    dumper = LazyPathDump(0, a_dir, os.environ)
    output = repr(dumper)
    assert executable_file in output
    assert "b_file" not in output


def test_discovery_via_version_specifier(session_cache: DiskCache) -> None:
    current = PythonInfo.current_system(session_cache)
    major, minor = current.version_info.major, current.version_info.minor

    spec = f">={major}.{minor}"
    interpreter = get_interpreter(spec, [], session_cache)
    assert interpreter is not None
    assert interpreter.version_info.major == major
    assert interpreter.version_info.minor >= minor

    spec = f">={major}.{minor},<{major}.{minor + 10}"
    interpreter = get_interpreter(spec, [], session_cache)
    assert interpreter is not None
    assert interpreter.version_info.major == major
    assert minor <= interpreter.version_info.minor < minor + 10

    spec = f"cpython>={major}.{minor}"
    interpreter = get_interpreter(spec, [], session_cache)
    if current.implementation == "CPython":  # pragma: no branch
        assert interpreter is not None
        assert interpreter.implementation == "CPython"


def _create_version_manager(tmp_path: Path, env_var: str) -> Path:
    root = tmp_path / env_var.lower()
    root.mkdir()
    (root / "shims").mkdir()
    return root


def _create_versioned_binary(root: Path, versions_path: tuple[str, ...], version: str, exe_name: str) -> Path:
    bin_dir = root.joinpath(*versions_path, version, "bin")
    bin_dir.mkdir(parents=True, exist_ok=True)
    exe = bin_dir / (f"{exe_name}.exe" if IS_WIN else exe_name)
    exe.touch()
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return exe


@pytest.mark.parametrize(
    ("env_var", "versions_path"),
    [
        pytest.param("PYENV_ROOT", ("versions",), id="pyenv"),
        pytest.param("MISE_DATA_DIR", ("installs", "python"), id="mise"),
        pytest.param("ASDF_DATA_DIR", ("installs", "python"), id="asdf"),
    ],
)
def test_shim_resolved_to_real_binary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_var: str,
    versions_path: tuple[str, ...],
) -> None:
    root = _create_version_manager(tmp_path, env_var)
    real_binary = _create_versioned_binary(root, versions_path, "2.7.18", "python2.7")
    shim = root / "shims" / ("python2.7.exe" if IS_WIN else "python2.7")
    shim.touch(mode=0o755)

    monkeypatch.setenv("PATH", str(root / "shims"))
    monkeypatch.setenv(env_var, str(root))
    monkeypatch.setenv("PYENV_VERSION", "2.7.18")
    monkeypatch.delenv("MISE_DATA_DIR", raising=False) if env_var != "MISE_DATA_DIR" else None
    monkeypatch.delenv("ASDF_DATA_DIR", raising=False) if env_var != "ASDF_DATA_DIR" else None
    monkeypatch.delenv("PYENV_ROOT", raising=False) if env_var != "PYENV_ROOT" else None

    with patch("python_discovery._discovery.PathPythonInfo.from_exe") as mock_from_exe:
        mock_from_exe.return_value = None
        get_interpreter("python2.7", [])
        assert mock_from_exe.call_args_list[0][0][0] == str(real_binary)


def test_shim_not_resolved_without_version_manager_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shims_dir = tmp_path / "shims"
    shims_dir.mkdir()
    shim = shims_dir / ("python2.7.exe" if IS_WIN else "python2.7")
    shim.touch(mode=0o755)

    monkeypatch.setenv("PATH", str(shims_dir))
    monkeypatch.delenv("PYENV_ROOT", raising=False)
    monkeypatch.delenv("MISE_DATA_DIR", raising=False)
    monkeypatch.delenv("ASDF_DATA_DIR", raising=False)

    with patch("python_discovery._discovery.PathPythonInfo.from_exe") as mock_from_exe:
        mock_from_exe.return_value = None
        get_interpreter("python2.7", [])
        assert mock_from_exe.call_args_list[0][0][0] == str(shim)


def test_shim_falls_through_when_binary_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _create_version_manager(tmp_path, "PYENV_ROOT")
    shim = root / "shims" / ("python2.7.exe" if IS_WIN else "python2.7")
    shim.touch(mode=0o755)

    monkeypatch.setenv("PATH", str(root / "shims"))
    monkeypatch.setenv("PYENV_ROOT", str(root))
    monkeypatch.setenv("PYENV_VERSION", "2.7.18")

    with patch("python_discovery._discovery.PathPythonInfo.from_exe") as mock_from_exe:
        mock_from_exe.return_value = None
        get_interpreter("python2.7", [])
        assert mock_from_exe.call_args_list[0][0][0] == str(shim)


def test_shim_uses_python_version_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _create_version_manager(tmp_path, "PYENV_ROOT")
    real_binary = _create_versioned_binary(root, ("versions",), "2.7.18", "python2.7")
    shim = root / "shims" / ("python2.7.exe" if IS_WIN else "python2.7")
    shim.touch(mode=0o755)
    (tmp_path / ".python-version").write_text(encoding="utf-8", data="2.7.18\n")

    monkeypatch.setenv("PATH", str(root / "shims"))
    monkeypatch.setenv("PYENV_ROOT", str(root))
    monkeypatch.delenv("PYENV_VERSION", raising=False)
    monkeypatch.chdir(tmp_path)

    with patch("python_discovery._discovery.PathPythonInfo.from_exe") as mock_from_exe:
        mock_from_exe.return_value = None
        get_interpreter("python2.7", [])
        assert mock_from_exe.call_args_list[0][0][0] == str(real_binary)


def test_shim_pyenv_version_env_takes_priority_over_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _create_version_manager(tmp_path, "PYENV_ROOT")
    _create_versioned_binary(root, ("versions",), "2.7.18", "python2.7")
    env_binary = _create_versioned_binary(root, ("versions",), "2.7.15", "python2.7")
    shim = root / "shims" / ("python2.7.exe" if IS_WIN else "python2.7")
    shim.touch(mode=0o755)
    (tmp_path / ".python-version").write_text(encoding="utf-8", data="2.7.18\n")

    monkeypatch.setenv("PATH", str(root / "shims"))
    monkeypatch.setenv("PYENV_ROOT", str(root))
    monkeypatch.setenv("PYENV_VERSION", "2.7.15")
    monkeypatch.chdir(tmp_path)

    with patch("python_discovery._discovery.PathPythonInfo.from_exe") as mock_from_exe:
        mock_from_exe.return_value = None
        get_interpreter("python2.7", [])
        assert mock_from_exe.call_args_list[0][0][0] == str(env_binary)


def test_shim_uses_global_version_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _create_version_manager(tmp_path, "PYENV_ROOT")
    real_binary = _create_versioned_binary(root, ("versions",), "2.7.18", "python2.7")
    shim = root / "shims" / ("python2.7.exe" if IS_WIN else "python2.7")
    shim.touch(mode=0o755)
    (root / "version").write_text(encoding="utf-8", data="2.7.18\n")
    workdir = tmp_path / "workdir"
    workdir.mkdir()

    monkeypatch.setenv("PATH", str(root / "shims"))
    monkeypatch.setenv("PYENV_ROOT", str(root))
    monkeypatch.delenv("PYENV_VERSION", raising=False)
    monkeypatch.chdir(workdir)

    with patch("python_discovery._discovery.PathPythonInfo.from_exe") as mock_from_exe:
        mock_from_exe.return_value = None
        get_interpreter("python2.7", [])
        assert mock_from_exe.call_args_list[0][0][0] == str(real_binary)


def test_shim_colon_separated_pyenv_version_picks_first_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _create_version_manager(tmp_path, "PYENV_ROOT")
    _create_versioned_binary(root, ("versions",), "2.7.18", "python2.7")
    second_binary = _create_versioned_binary(root, ("versions",), "2.7.15", "python2.7")
    shim = root / "shims" / ("python2.7.exe" if IS_WIN else "python2.7")
    shim.touch(mode=0o755)

    monkeypatch.setenv("PATH", str(root / "shims"))
    monkeypatch.setenv("PYENV_ROOT", str(root))
    monkeypatch.setenv("PYENV_VERSION", "3.9.1:2.7.15")

    with patch("python_discovery._discovery.PathPythonInfo.from_exe") as mock_from_exe:
        mock_from_exe.return_value = None
        get_interpreter("python2.7", [])
        assert mock_from_exe.call_args_list[0][0][0] == str(second_binary)


def test_predicate_filters_interpreters(session_cache: DiskCache) -> None:
    result = get_interpreter(sys.executable, [], session_cache, predicate=lambda _: False)
    assert result is None


def test_predicate_accepts_interpreter(session_cache: DiskCache) -> None:
    result = get_interpreter(sys.executable, [], session_cache, predicate=lambda _: True)
    assert result is not None
    assert result.executable == sys.executable


def test_predicate_none_is_noop(session_cache: DiskCache) -> None:
    result = get_interpreter(sys.executable, [], session_cache, predicate=None)
    assert result is not None
    assert result.executable == sys.executable


def test_predicate_with_fallback_specs(session_cache: DiskCache) -> None:
    current = PythonInfo.current_system(session_cache)
    major, minor = current.version_info.major, current.version_info.minor
    proposed: list[str] = []

    def reject_first(info: PythonInfo) -> bool:
        proposed.append(str(info.executable))
        return len(proposed) > 1

    threaded = "t" if current.free_threaded else ""
    result = get_interpreter([f"{major}.{minor}{threaded}", sys.executable], [], session_cache, predicate=reject_first)
    # rejecting the first proposal must not abort discovery; a later proposal (same or fallback spec) is accepted -
    # on hosts where every alias resolves to one interpreter the fallback re-proposes it, so executables may match
    assert result is not None
    assert len(proposed) > 1
    assert str(result.executable) == proposed[-1]


# no interpreter answers to this, so discovery walks every source instead of stopping at the running one
_NO_UV_MATCH: Final[str] = "3.99"


@pytest.fixture
def uv_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A throwaway home, with every directory variable uv consults pointed into it or unset."""
    for var in ("UV_PYTHON_INSTALL_DIR", "XDG_DATA_HOME", "APPDATA"):
        monkeypatch.delenv(var, raising=False)
    for var in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(var, str(tmp_path))
    monkeypatch.setenv("PATH", "")
    return tmp_path


@pytest.fixture
def uv_plant() -> Callable[[Path], str]:
    """Create a uv install under a store root and return the executable discovery should reach for."""

    def _plant(root: Path) -> str:
        (bin_dir := root / "some-py-impl" / "bin").mkdir(parents=True)
        (executable := bin_dir / "python").touch()
        return str(executable)

    return _plant


@pytest.fixture
def uv_probed(mocker: MockerFixture) -> Callable[..., list[str]]:
    """Run a discovery with the interrogation subprocess stubbed out, reporting the executables it reached for."""
    from_exe = mocker.patch("python_discovery._discovery.PathPythonInfo.from_exe", return_value=None)

    def _probed(**kwargs: object) -> list[str]:
        get_interpreter(_NO_UV_MATCH, [], **kwargs)
        return [call.args[0] for call in from_exe.call_args_list]

    return _probed


@pytest.mark.parametrize("expand_user", [True, False], ids=["expands-user", "absolute"])
def test_discovery_uv_store_install_dir_overrides_the_platform_default(
    uv_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    uv_plant: Callable[[Path], str],
    uv_probed: Callable[..., list[str]],
    expand_user: bool,
) -> None:
    monkeypatch.setenv("UV_PYTHON_INSTALL_DIR", "~/store" if expand_user else str(uv_home / "store"))
    uv_plant(uv_home / ".local" / "share" / "uv" / "python")
    executable = uv_plant(uv_home / "store")

    assert uv_probed() == [executable]


@pytest.mark.parametrize(
    ("platform", "extra_env", "expected"),
    [
        pytest.param("win32", {"APPDATA": "~/roaming"}, ["~/roaming/uv/data", "~/roaming/uv"], id="windows"),
        pytest.param("win32", {}, ["~/AppData/Roaming/uv/data", "~/AppData/Roaming/uv"], id="windows-without-appdata"),
        pytest.param("darwin", {}, ["~/Library/Application Support/uv", "~/.local/share/uv"], id="macos"),
        pytest.param(
            "darwin",
            {"XDG_DATA_HOME": "~/xdg"},
            ["~/Library/Application Support/uv", "~/xdg/uv"],
            id="macos-with-xdg",
        ),
        pytest.param("linux", {}, ["~/.local/share/uv"], id="linux"),
        pytest.param("linux", {"XDG_DATA_HOME": "~/xdg"}, ["~/xdg/uv"], id="linux-with-xdg"),
        pytest.param("linux", {"XDG_DATA_HOME": "relative"}, ["~/.local/share/uv"], id="linux-ignores-relative-xdg"),
    ],
)
@pytest.mark.usefixtures("uv_home")
def test_discovery_uv_store_roots_per_platform(
    monkeypatch: pytest.MonkeyPatch,
    uv_plant: Callable[[Path], str],
    uv_probed: Callable[..., list[str]],
    platform: str,
    extra_env: dict[str, str],
    expected: list[str],
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    for name, value in extra_env.items():
        monkeypatch.setenv(name, str(Path(value).expanduser()))
    executables = [uv_plant(Path(state_dir).expanduser() / "python") for state_dir in expected]

    assert uv_probed() == executables


def test_discovery_uv_store_windows_ignores_xdg_data_home(
    uv_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    uv_plant: Callable[[Path], str],
    uv_probed: Callable[..., list[str]],
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("XDG_DATA_HOME", str(uv_home / "xdg"))
    uv_plant(uv_home / "xdg" / "uv" / "python")
    executable = uv_plant(uv_home / "AppData" / "Roaming" / "uv" / "python")

    assert uv_probed() == [executable]


def test_discovery_uv_store_reads_the_env_argument(
    uv_home: Path, uv_plant: Callable[[Path], str], uv_probed: Callable[..., list[str]]
) -> None:
    executable = uv_plant(uv_home / "store")

    assert uv_probed(env={"PATH": "", "UV_PYTHON_INSTALL_DIR": str(uv_home / "store")}) == [executable]


@pytest.mark.usefixtures("uv_home")
def test_discovery_uv_store_missing_root_is_not_an_error(uv_probed: Callable[..., list[str]]) -> None:
    assert uv_probed() == []


def test_discovery_uv_store_is_searched_after_path(
    uv_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    uv_plant: Callable[[Path], str],
    uv_probed: Callable[..., list[str]],
) -> None:
    store_executable = uv_plant(uv_home / ".local" / "share" / "uv" / "python")
    (path_dir := uv_home / "path-bin").mkdir()
    (path_executable := path_dir / f"python{_NO_UV_MATCH}{'.exe' if IS_WIN else ''}").touch()
    monkeypatch.setenv("PATH", str(path_dir))

    assert uv_probed() == [str(path_executable), store_executable]
