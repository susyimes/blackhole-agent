from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, TracebackType
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

    from typing_extensions import Self


def _create_winreg_mock() -> ModuleType:
    """Create a mock winreg module that works on all platforms."""
    winreg = ModuleType("winreg")
    winreg.HKEY_CURRENT_USER = 0x80000001  # ty: ignore[unresolved-attribute]
    winreg.HKEY_LOCAL_MACHINE = 0x80000002  # ty: ignore[unresolved-attribute]
    winreg.KEY_READ = 0x20019  # ty: ignore[unresolved-attribute]
    winreg.KEY_WOW64_64KEY = 0x0100  # ty: ignore[unresolved-attribute]
    winreg.KEY_WOW64_32KEY = 0x0200  # ty: ignore[unresolved-attribute]
    winreg.EnumKey = MagicMock()  # ty: ignore[unresolved-attribute]
    winreg.QueryValueEx = MagicMock()  # ty: ignore[unresolved-attribute]
    winreg.OpenKeyEx = MagicMock()  # ty: ignore[unresolved-attribute]
    return winreg


def _load_registry_data(
    winreg: ModuleType,
) -> tuple[
    dict[object, dict[int, object]],
    dict[object, dict[str, object]],
    dict[object, dict[str, object]],
    dict[tuple[object, ...], object],
]:
    """Load winreg mock values using the given (possibly mock) winreg module."""
    loc: dict[str, object] = {}
    glob: dict[str, object] = {"winreg": winreg}
    mock_value_str = (Path(__file__).parent / "winreg_mock_values.py").read_text(encoding="utf-8")
    exec(mock_value_str, glob, loc)  # ruff:ignore[exec-builtin]
    return loc["enum_collect"], loc["value_collect"], loc["key_open"], loc["hive_open"]  # type: ignore[return-value]


class _Key:
    def __init__(self, value: object) -> None:
        self.value = value

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None
    ) -> None:
        return None


def _make_enum_key(enum_collect: dict[object, dict[int, object]]) -> object:
    def _enum_key(key: object, at: int) -> str:
        key_id = key.value if isinstance(key, _Key) else key
        result = enum_collect[key_id][at]
        if isinstance(result, OSError):
            raise result
        return result  # type: ignore[return-value]

    return _enum_key


def _make_query_value_ex(value_collect: dict[object, dict[str, object]]) -> object:
    def _query_value_ex(key: object, value_name: str) -> object:
        key_id = key.value if isinstance(key, _Key) else key
        result = value_collect[key_id][value_name]
        if isinstance(result, OSError):
            raise result
        return result

    return _query_value_ex


def _make_open_key_ex(key_open: dict[object, dict[str, object]], hive_open: dict[tuple[object, ...], object]) -> object:
    @contextmanager
    def _open_key_ex(*args: object) -> Generator[_Key | object]:
        if len(args) == 2:
            key, value = args
            key_id = key.value if isinstance(key, _Key) else key
            result = _Key(key_open[key_id][value])
        elif len(args) == 4:
            result = hive_open[args]
        else:
            raise RuntimeError
        value = result.value if isinstance(result, _Key) else result
        if isinstance(value, OSError):
            raise value
        yield result

    return _open_key_ex


@pytest.fixture
def _mock_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    if sys.platform != "win32":
        winreg = _create_winreg_mock()
        monkeypatch.setitem(sys.modules, "winreg", winreg)
    else:
        import winreg

    enum_collect, value_collect, key_open, hive_open = _load_registry_data(winreg)

    monkeypatch.setattr(winreg, "EnumKey", _make_enum_key(enum_collect))
    monkeypatch.setattr(winreg, "QueryValueEx", _make_query_value_ex(value_collect))
    monkeypatch.setattr(winreg, "OpenKeyEx", _make_open_key_ex(key_open, hive_open))
    real_exists = os.path.exists

    def _mock_exists(path: str) -> bool:
        if isinstance(path, str) and ("\\" in path or path.startswith(("C:", "Z:"))):
            return True
        return real_exists(path)

    monkeypatch.setattr("os.path.exists", _mock_exists)


def _mock_pyinfo(major: int, minor: int, arch: int, exe: str, threaded: bool = False) -> MagicMock:
    from python_discovery._py_info import VersionInfo

    info = MagicMock()
    info.base_prefix = str(Path(exe).parent)
    info.executable = info.original_executable = info.system_executable = exe
    info.implementation = "CPython"
    info.architecture = arch
    info.version_info = VersionInfo(major, minor, 0, "final", 0)
    info.free_threaded = threaded
    info.sysconfig_platform = "win-amd64" if arch == 64 else "win32"
    info.machine = "x86_64" if arch == 64 else "x86"

    def satisfies(spec: object, _impl_must_match: bool = False) -> bool:
        if spec.implementation is not None and spec.implementation.lower() != "cpython":
            return False
        if spec.architecture is not None and spec.architecture != arch:
            return False
        if spec.free_threaded is not None and spec.free_threaded != threaded:
            return False
        if spec.major is not None and spec.major != major:
            return False
        return not (spec.minor is not None and spec.minor != minor)

    info.satisfies = satisfies
    return info


@pytest.fixture
def _populate_pyinfo_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    from python_discovery._cached_py_info import _CACHE

    python_core_path = "C:\\Users\\user\\AppData\\Local\\Programs\\Python"
    interpreters = [
        ("ContinuumAnalytics", 3, 10, 32, False, "C:\\Users\\user\\Miniconda3\\python.exe"),
        ("ContinuumAnalytics", 3, 10, 64, False, "C:\\Users\\user\\Miniconda3-64\\python.exe"),
        ("PythonCore", 3, 9, 64, False, f"{python_core_path}\\Python36\\python.exe"),
        ("PythonCore", 3, 9, 64, False, f"{python_core_path}\\Python36\\python.exe"),
        ("PythonCore", 3, 5, 64, False, f"{python_core_path}\\Python35\\python.exe"),
        ("PythonCore", 3, 9, 64, False, f"{python_core_path}\\Python36\\python.exe"),
        ("PythonCore", 3, 7, 32, False, f"{python_core_path}\\Python37-32\\python.exe"),
        ("PythonCore", 3, 12, 64, False, f"{python_core_path}\\Python312\\python.exe"),
        ("PythonCore", 3, 13, 64, True, f"{python_core_path}\\Python313\\python3.13t.exe"),
        ("PythonCore", 2, 7, 64, False, "C:\\Python27\\python.exe"),
        ("PythonCore", 3, 4, 64, False, "C:\\Python34\\python.exe"),
        ("CompanyA", 3, 6, 64, False, "Z:\\CompanyA\\Python\\3.6\\python.exe"),
    ]
    for _, major, minor, arch, threaded, exe in interpreters:
        info = _mock_pyinfo(major, minor, arch, exe, threaded)
        monkeypatch.setitem(_CACHE, Path(info.executable), info)
