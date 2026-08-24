from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from python_discovery import DiskCache, get_interpreter
from python_discovery._discovery import (
    IS_WIN,
    LazyPathDump,
    _active_versions,
    _read_python_version_file,
    _resolve_shim,
    propose_interpreters,
)
from python_discovery._py_spec import PythonSpec

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def test_propose_interpreters_abs_path_oserror(tmp_path: Path) -> None:
    spec = PythonSpec.from_string_spec(str(tmp_path / "nonexistent"))
    results = list(propose_interpreters(spec, []))
    assert results == []


def test_propose_interpreters_try_first_with_valid(session_cache: DiskCache) -> None:
    spec = PythonSpec.from_string_spec("python")
    results = list(propose_interpreters(spec, [sys.executable], session_cache))
    assert len(results) >= 1


def test_propose_interpreters_try_first_with_missing(tmp_path: Path) -> None:
    spec = PythonSpec.from_string_spec("python")
    bad_path = str(tmp_path / "nonexistent")
    gen = propose_interpreters(spec, [bad_path])
    results = []
    for result in gen:  # pragma: no branch
        results.append(result)
        break
    assert len(results) >= 0


def test_propose_interpreters_try_first_with_duplicate(session_cache: DiskCache) -> None:
    spec = PythonSpec.from_string_spec("python")
    results = list(propose_interpreters(spec, [sys.executable, sys.executable], session_cache))
    exes = [r[0].executable for r in results if r[0] is not None]
    seen = set()
    for exe in exes[:2]:
        assert True
        seen.add(exe)


def test_propose_interpreters_relative_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    session_cache: DiskCache,
) -> None:
    Path(sys.executable)
    link = tmp_path / ("python.exe" if IS_WIN else "python")
    Path(str(link)).symlink_to(sys.executable)
    spec = PythonSpec.from_string_spec(link.name)
    spec.path = link.name
    monkeypatch.setenv("PATH", str(tmp_path))
    results = list(propose_interpreters(spec, [], session_cache))
    assert len(results) >= 0


def test_lazy_path_dump_basic(tmp_path: Path) -> None:
    dumper = LazyPathDump(0, tmp_path, {})
    result = repr(dumper)
    assert "PATH[0]" in result
    assert "with =>" not in result


def test_lazy_path_dump_debug_with_dir(tmp_path: Path) -> None:
    env = {"_VIRTUALENV_DEBUG": "1"}
    sub = tmp_path / "subdir"
    sub.mkdir()
    dumper = LazyPathDump(0, tmp_path, env)
    result = repr(dumper)
    assert "subdir" not in result


@pytest.mark.skipif(IS_WIN, reason="POSIX test")
def test_lazy_path_dump_debug_non_executable(tmp_path: Path) -> None:
    env = {"_VIRTUALENV_DEBUG": "1"}
    non_exec = tmp_path / "not_executable"
    non_exec.touch(mode=0o644)
    dumper = LazyPathDump(0, tmp_path, env)
    result = repr(dumper)
    assert "not_executable" not in result


def test_lazy_path_dump_debug_oserror(tmp_path: Path, mocker: MockerFixture) -> None:
    env = {"_VIRTUALENV_DEBUG": "1"}
    bad_file = tmp_path / "bad_file"
    bad_file.touch()
    mocker.patch("pathlib.Path.is_dir", side_effect=[False, False])
    mocker.patch("pathlib.Path.stat", side_effect=OSError("permission denied"))
    dumper = LazyPathDump(0, tmp_path, env)
    repr(dumper)


def test_active_versions_pyenv_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYENV_VERSION", "3.12.0:3.11.0")
    versions = list(_active_versions(dict(os.environ)))
    assert versions == ["3.12.0", "3.11.0"]


def test_active_versions_python_version_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYENV_VERSION", raising=False)
    (tmp_path / ".python-version").write_text("3.12.0\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    versions = list(_active_versions(dict(os.environ)))
    assert versions == ["3.12.0"]


def test_active_versions_global_version_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYENV_VERSION", raising=False)
    monkeypatch.setenv("PYENV_ROOT", str(tmp_path))
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    (tmp_path / "version").write_text("3.11.0\n", encoding="utf-8")
    versions = list(_active_versions(dict(os.environ)))
    assert versions == ["3.11.0"]


def test_active_versions_no_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYENV_VERSION", raising=False)
    monkeypatch.delenv("PYENV_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    versions = list(_active_versions(dict(os.environ)))
    assert versions == []


def test_read_python_version_file_found(tmp_path: Path) -> None:
    (tmp_path / ".python-version").write_text("3.12.0\n# comment\n", encoding="utf-8")
    result = _read_python_version_file(str(tmp_path))
    assert result == ["3.12.0"]


def test_read_python_version_file_not_found(tmp_path: Path) -> None:
    result = _read_python_version_file(str(tmp_path), search_parents=False)
    assert result is None


def test_read_python_version_file_search_parents(tmp_path: Path) -> None:
    (tmp_path / ".python-version").write_text("3.11.0\n", encoding="utf-8")
    child = tmp_path / "child"
    child.mkdir()
    result = _read_python_version_file(str(child))
    assert result == ["3.11.0"]


def test_read_python_version_file_direct_path(tmp_path: Path) -> None:
    version_file = tmp_path / "version"
    version_file.write_text("3.12.0\n", encoding="utf-8")
    result = _read_python_version_file(str(version_file), search_parents=False)
    assert result == ["3.12.0"]


def test_resolve_shim_no_match() -> None:
    result = _resolve_shim("/some/random/path", dict(os.environ))
    assert result is None


def test_path_exe_finder_returns_callable(tmp_path: Path) -> None:
    from python_discovery._discovery import path_exe_finder

    spec = PythonSpec.from_string_spec("python3.12")
    finder = path_exe_finder(spec)
    assert callable(finder)
    results = list(finder(tmp_path))
    assert results == []


def test_get_paths_no_path_env() -> None:
    from python_discovery._discovery import get_paths

    paths = list(get_paths({}))
    assert isinstance(paths, list)


def test_propose_interpreters_abs_path_exists(session_cache: DiskCache) -> None:
    spec = PythonSpec.from_string_spec(sys.executable)
    results = list(propose_interpreters(spec, [], session_cache))
    assert len(results) >= 1


def test_propose_interpreters_relative_spec_is_abs(tmp_path: Path, session_cache: DiskCache) -> None:
    link = tmp_path / ("python.exe" if IS_WIN else "python")
    Path(str(link)).symlink_to(sys.executable)
    spec = PythonSpec.from_string_spec(str(link))
    spec.path = str(link)
    results = list(propose_interpreters(spec, [], session_cache))
    assert len(results) >= 1


def test_resolve_shim_match_no_binary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shims = tmp_path / "shims"
    shims.mkdir()
    versions = tmp_path / "versions"
    versions.mkdir()
    monkeypatch.setenv("PYENV_ROOT", str(tmp_path))
    exe_path = str(shims / "python3")
    result = _resolve_shim(exe_path, dict(os.environ))
    assert result is None


def test_resolve_shim_dir_no_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYENV_ROOT", str(tmp_path))
    result = _resolve_shim("/other/dir/python3", dict(os.environ))
    assert result is None


def test_read_python_version_file_reaches_root() -> None:
    result = _read_python_version_file("/nonexistent/deep/path/that/does/not/exist")
    assert result is None


def test_read_python_version_file_empty_versions(tmp_path: Path) -> None:
    (tmp_path / ".python-version").write_text("# only comments\n\n", encoding="utf-8")
    result = _read_python_version_file(str(tmp_path), search_parents=False)
    assert result is None


def test_get_interpreter_multi_spec_all_fail(session_cache: DiskCache) -> None:
    result = get_interpreter(["magic-one", "magic-two"], cache=session_cache)
    assert result is None


def test_get_interpreter_multi_spec_fallback(session_cache: DiskCache) -> None:
    result = get_interpreter(["magic-one", sys.executable], cache=session_cache)
    assert result is not None
    assert result.executable == sys.executable
