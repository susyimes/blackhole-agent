from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from python_discovery import DiskCache, PythonInfo

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture(scope="session")
def session_cache(tmp_path_factory: pytest.TempPathFactory) -> DiskCache:
    return DiskCache(tmp_path_factory.mktemp("python-discovery-cache"))


@pytest.fixture(autouse=True)
def _ensure_py_info_cache_empty(session_cache: DiskCache) -> Generator[None]:
    PythonInfo.clear_cache(session_cache)
    yield
    PythonInfo.clear_cache(session_cache)


@pytest.fixture
def _skip_if_test_in_system(session_cache: DiskCache) -> None:
    current = PythonInfo.current(session_cache)
    if current.system_executable is not None:  # pragma: no cover
        msg = "test not valid if run under system"
        raise pytest.skip.Exception(msg)
