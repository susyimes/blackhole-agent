from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import sysconfig
from itertools import takewhile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import vermin

import python_discovery
from python_discovery import PythonInfo
from python_discovery._py_info import VersionInfo

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytest_mock import MockerFixture

SCRIPT = Path(python_discovery.__file__).parent / "_py_info_collect.py"


def test_script_parses_down_to_python27() -> None:
    py2, py3 = vermin.detect(SCRIPT.read_text(encoding="utf-8"))
    assert py2 is not None, "script no longer parses on Python 2.7, the version gate cannot run there"
    assert py2 <= (2, 7)
    assert py3 is not None
    assert py3 <= (3, 6), "script grew a requirement newer than the collection floor"


def test_script_version_gate_precedes_imports() -> None:
    body = ast.parse(SCRIPT.read_text(encoding="utf-8")).body
    before_gate = takewhile(lambda node: not isinstance(node, ast.If), body)
    imported = [
        alias.name for node in before_gate if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names
    ]
    assert imported == ["sys"], "only sys may load before the version gate; Python 3.0/3.1 lack sysconfig"


def _run_script(*args: str) -> str:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=True).stdout


@pytest.mark.parametrize(
    ("args", "start", "end"),
    [
        pytest.param((), "", "", id="no-cookies"),
        pytest.param(("startcookie",), "startcookie", "", id="start-only"),
        pytest.param(("startcookie", "endcookie"), "startcookie", "endcookie", id="both-cookies"),
    ],
)
def test_script_wraps_payload_in_reversed_cookies(args: tuple[str, ...], start: str, end: str) -> None:
    out = _run_script(*args)
    prefix, suffix = start[::-1], end[::-1]
    assert out.startswith(prefix)
    assert out.endswith(suffix)
    payload = json.loads(out[len(prefix) : len(out) - len(suffix)])
    assert payload["version_info"]["major"] == sys.version_info.major


def test_script_payload_matches_in_process_collection() -> None:
    assert set(json.loads(_run_script())) == set(PythonInfo().to_dict())


def test_script_payload_loads_as_python_info() -> None:
    info = PythonInfo.from_json(_run_script())
    assert tuple(info.version_info[:3]) == tuple(sys.version_info[:3])
    assert info.executable == sys.executable


@pytest.fixture
def no_framework(mocker: MockerFixture) -> None:
    get_config_var = sysconfig.get_config_var
    mocker.patch.object(
        sysconfig,
        "get_config_var",
        side_effect=lambda name: "" if name == "PYTHONFRAMEWORK" else get_config_var(name),
    )


@pytest.fixture
def not_a_venv(mocker: MockerFixture) -> None:
    mocker.patch.object(sys, "real_prefix", None, create=True)
    mocker.patch.object(sys, "base_prefix", sys.prefix)


def _layout_regular_file(tmp_path: Path) -> tuple[Path, Path]:
    exe = tmp_path / "python"
    exe.touch()
    return exe, exe


def _layout_broken_symlink(tmp_path: Path) -> tuple[Path, Path]:
    link = tmp_path / "python"
    link.symlink_to(tmp_path / "missing")
    return link, link


def _layout_absolute_symlink(tmp_path: Path) -> tuple[Path, Path]:
    exe = tmp_path / "install" / "bin" / "python3.12"
    exe.parent.mkdir(parents=True)
    exe.touch()
    link = tmp_path / "symdir" / "python3"
    link.parent.mkdir()
    link.symlink_to(exe)
    return link, exe


def _layout_relative_chain(tmp_path: Path) -> tuple[Path, Path]:
    exe = tmp_path / "python3.12"
    exe.touch()
    (tmp_path / "python3").symlink_to("python3.12")
    link = tmp_path / "python"
    link.symlink_to("python3")
    return link, exe


def _layout_tree_symlink(tmp_path: Path) -> tuple[Path, Path]:
    real_bin = tmp_path / "install" / "bin"
    real_bin.mkdir(parents=True)
    (real_bin / "python3").touch()
    tree_link = tmp_path / "tree"
    tree_link.symlink_to(tmp_path / "install")
    via_tree = tree_link / "bin" / "python3"
    return via_tree, via_tree


def _layout_normpath_mismatch(tmp_path: Path) -> tuple[Path, Path]:
    real_dir = tmp_path / "deep" / "real"
    real_dir.mkdir(parents=True)
    (tmp_path / "deep" / "exe").touch()
    (real_dir / "python").symlink_to("../exe")
    dir_link = tmp_path / "link"
    dir_link.symlink_to(real_dir)
    via_link = dir_link / "python"
    return via_link, via_link


def _layout_stdlib_landmark(tmp_path: Path) -> tuple[Path, Path]:
    exe = tmp_path / "install" / "bin" / "python3.12"
    exe.parent.mkdir(parents=True)
    exe.touch()
    alias_bin = tmp_path / "alias" / "bin"
    alias_bin.mkdir(parents=True)
    landmark = tmp_path / "alias" / "lib" / Path(os.__file__).parent.name / "os.py"
    landmark.parent.mkdir(parents=True)
    landmark.touch()
    link = alias_bin / "python3"
    link.symlink_to(exe)
    return link, link


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX only")
@pytest.mark.usefixtures("no_framework", "not_a_venv")
@pytest.mark.parametrize(
    "layout",
    [
        pytest.param(_layout_regular_file, id="regular-file"),
        pytest.param(_layout_broken_symlink, id="broken-symlink"),
        pytest.param(_layout_absolute_symlink, id="absolute-symlink"),
        pytest.param(_layout_relative_chain, id="relative-chain"),
        pytest.param(_layout_tree_symlink, id="tree-preserved"),
        pytest.param(_layout_normpath_mismatch, id="normpath-mismatch"),
        pytest.param(_layout_stdlib_landmark, id="stdlib-landmark-kept"),
    ],
)
def test_system_executable_resolves_executable_symlink_only(
    tmp_path: Path,
    mocker: MockerFixture,
    layout: Callable[[Path], tuple[Path, Path]],
) -> None:
    path, expected = layout(tmp_path)
    mocker.patch.object(sys, "executable", str(path))
    assert PythonInfo().system_executable == str(expected)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX only")
@pytest.mark.usefixtures("not_a_venv")
def test_system_executable_framework_symlink_kept(tmp_path: Path, mocker: MockerFixture) -> None:
    link, _exe = _layout_absolute_symlink(tmp_path)
    get_config_var = sysconfig.get_config_var
    mocker.patch.object(
        sysconfig,
        "get_config_var",
        side_effect=lambda name: "Python" if name == "PYTHONFRAMEWORK" else get_config_var(name),
    )
    mocker.patch.object(sys, "executable", str(link))
    assert PythonInfo().system_executable == str(link)


def _old_style_virtualenv(mocker: MockerFixture, _tmp_path: Path) -> None:
    mocker.patch.object(sys, "real_prefix", "/some/real/prefix", create=True)


def _venv_without_base_executable(mocker: MockerFixture, _tmp_path: Path) -> None:
    _venv(mocker)
    mocker.patch.object(sys, "_base_executable", None, create=True)


def _venv_base_executable_is_self(mocker: MockerFixture, _tmp_path: Path) -> None:
    _venv(mocker)
    mocker.patch.object(sys, "_base_executable", sys.executable, create=True)


def _venv_missing_base_before_311(mocker: MockerFixture, tmp_path: Path) -> None:
    _venv(mocker)
    mocker.patch.object(sys, "_base_executable", str(tmp_path / "python"), create=True)
    mocker.patch.object(sys, "version_info", VersionInfo(3, 9, 0, "final", 0))


def _venv_missing_base_no_candidates(mocker: MockerFixture, tmp_path: Path) -> None:
    _venv(mocker)
    mocker.patch.object(sys, "_base_executable", str(tmp_path / "python"), create=True)
    mocker.patch.object(sys, "version_info", VersionInfo(3, 12, 0, "final", 0))


def _venv(mocker: MockerFixture) -> None:
    mocker.patch.object(sys, "real_prefix", None, create=True)
    mocker.patch.object(sys, "base_prefix", "/different/prefix")


@pytest.mark.parametrize(
    "state",
    [
        pytest.param(_old_style_virtualenv, id="old-style-virtualenv"),
        pytest.param(_venv_without_base_executable, id="no-base-executable"),
        pytest.param(_venv_base_executable_is_self, id="base-executable-is-self"),
        pytest.param(_venv_missing_base_before_311, id="missing-base-before-311"),
        pytest.param(_venv_missing_base_no_candidates, id="missing-base-no-candidates"),
    ],
)
def test_system_executable_undetermined(
    mocker: MockerFixture, tmp_path: Path, state: Callable[[MockerFixture, Path], None]
) -> None:
    state(mocker, tmp_path)
    assert PythonInfo().system_executable is None


def test_system_executable_from_existing_base(mocker: MockerFixture, tmp_path: Path) -> None:
    base = tmp_path / "python3.12"
    base.touch()
    _venv(mocker)
    mocker.patch.object(sys, "_base_executable", str(base), create=True)
    assert PythonInfo().system_executable == str(base)


def test_system_executable_versioned_fallback(mocker: MockerFixture, tmp_path: Path) -> None:
    _venv_missing_base_no_candidates(mocker, tmp_path)
    versioned = tmp_path / "python3"
    versioned.touch()
    assert PythonInfo().system_executable == str(versioned)


def test_system_executable_pypy_fallback(mocker: MockerFixture, tmp_path: Path) -> None:
    _venv_missing_base_no_candidates(mocker, tmp_path)
    mocker.patch("platform.python_implementation", return_value="PyPy")
    mocker.patch.object(sys, "pypy_version_info", (7, 3, 11, "final", 0), create=True)
    pypy = tmp_path / "pypy3"
    pypy.touch()
    assert PythonInfo().system_executable == str(pypy)


def test_tcl_tk_libs_none_without_env(mocker: MockerFixture) -> None:
    mocker.patch.dict(os.environ)
    os.environ.pop("TCL_LIBRARY", None)
    info = PythonInfo()
    assert (info.tcl_lib, info.tk_lib) == (None, None)


class _TclError(Exception):
    """Stands in for tkinter.TclError; an except clause needs a real exception type."""


def _fake_tkinter(mocker: MockerFixture, eval_side_effect: object) -> None:
    module = mocker.MagicMock(TclError=_TclError, **{"Tcl.return_value.eval.side_effect": eval_side_effect})
    mocker.patch.dict(sys.modules, {"tkinter": module})


def test_tcl_tk_libs_queried_with_env(tmp_path: Path, mocker: MockerFixture) -> None:
    tk_dir = tmp_path / "tk8.6"
    tk_dir.mkdir()
    responses = {"info library": "/tcl-lib", "set tk_library": str(tk_dir)}
    _fake_tkinter(mocker, responses.__getitem__)
    mocker.patch.dict(os.environ, {"TCL_LIBRARY": str(tmp_path)})
    info = PythonInfo()
    assert (info.tcl_lib, info.tk_lib) == ("/tcl-lib", str(tk_dir))


def test_tcl_tk_libs_none_on_tcl_error(tmp_path: Path, mocker: MockerFixture) -> None:
    _fake_tkinter(mocker, _TclError("fail"))
    mocker.patch.dict(os.environ, {"TCL_LIBRARY": str(tmp_path)})
    info = PythonInfo()
    assert (info.tcl_lib, info.tk_lib) == (None, None)


def test_system_stdlib_empty_when_scheme_lacks_path(mocker: MockerFixture) -> None:
    names = tuple(name for name in sysconfig.get_path_names() if name not in {"stdlib", "platstdlib"})
    mocker.patch.object(sysconfig, "get_path_names", return_value=names)
    info = PythonInfo()
    assert (info.system_stdlib, info.system_stdlib_platform) == ("", "")
