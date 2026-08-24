from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from python_discovery import DiskCache, PythonInfo, iter_interpreters
from python_discovery._discovery import IS_WIN

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from pytest_mock import MockerFixture


@pytest.fixture
def uv_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Empty uv install root with environment variables pointing at it."""
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    root = tmp_path / "uv-python"
    root.mkdir()
    monkeypatch.setenv("UV_PYTHON_INSTALL_DIR", str(root))
    return root


@pytest.fixture
def uv_install(uv_dir: Path) -> Callable[..., None]:
    def _install(*relative: str) -> None:
        for entry in relative:
            (path := uv_dir / entry).parent.mkdir(parents=True, exist_ok=True)
            path.touch()

    return _install


@pytest.fixture
def uv_probed(
    uv_dir: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
) -> Callable[[str | None], list[str]]:
    """Stub out the interrogation subprocess, so a run reports the executables discovery reached for."""
    monkeypatch.setenv("PATH", "")
    from_exe = mocker.patch("python_discovery._discovery.PathPythonInfo.from_exe", return_value=None)

    def _probed(key: str | None) -> list[str]:
        list(iter_interpreters(key))
        return [Path(call.args[0]).relative_to(uv_dir).as_posix() for call in from_exe.call_args_list]

    return _probed


def test_iter_interpreters_returns_iterator(session_cache: DiskCache) -> None:
    result: Iterator[PythonInfo] = iter_interpreters(sys.executable, cache=session_cache)
    assert iter(result) is result


def test_iter_interpreters_with_abs_path_yields_one(session_cache: DiskCache) -> None:
    results = list(iter_interpreters(sys.executable, cache=session_cache))
    assert len(results) == 1
    assert results[0].executable == sys.executable


def test_iter_interpreters_sequence_dedups_across_keys(session_cache: DiskCache) -> None:
    results = list(iter_interpreters([sys.executable, sys.executable], cache=session_cache))
    assert len(results) == 1


@pytest.mark.parametrize(
    ("predicate", "expected_count"),
    [
        pytest.param(None, 1, id="none-is-noop"),
        pytest.param(lambda _: True, 1, id="accepts-all"),
        pytest.param(lambda _: False, 0, id="rejects-all"),
    ],
)
def test_iter_interpreters_predicate(
    session_cache: DiskCache,
    predicate: Callable[[PythonInfo], bool] | None,
    expected_count: int,
) -> None:
    results = list(iter_interpreters(sys.executable, cache=session_cache, predicate=predicate))
    assert len(results) == expected_count


@pytest.mark.parametrize(
    "key_factory",
    [
        pytest.param(lambda: uuid4().hex, id="filename-cannot-match"),
        pytest.param(lambda: ">=999", id="version-cannot-match"),
    ],
)
def test_iter_interpreters_filters_to_empty(
    session_cache: DiskCache,
    key_factory: Callable[[], str],
) -> None:
    assert list(iter_interpreters(key_factory(), cache=session_cache)) == []


@pytest.mark.usefixtures("uv_dir")
def test_iter_interpreters_no_key_includes_running_interpreter(session_cache: DiskCache) -> None:
    real_self = os.path.realpath(sys.executable)
    results = list(iter_interpreters(cache=session_cache))
    assert any(os.path.realpath(info.executable) == real_self for info in results)


@pytest.mark.usefixtures("uv_dir")
def test_iter_interpreters_dedups_symlinks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    session_cache: DiskCache,
) -> None:
    suffix = ".exe" if IS_WIN else ""
    for name in ("python3", "python3.99"):
        Path(str(tmp_path / f"{name}{suffix}")).symlink_to(sys.executable)
    pyvenv_cfg = Path(sys.executable).parents[1] / "pyvenv.cfg"
    with contextlib.suppress(FileNotFoundError):
        (tmp_path / pyvenv_cfg.name).write_bytes(pyvenv_cfg.read_bytes())
    monkeypatch.setenv("PATH", os.pathsep.join([str(tmp_path), os.environ.get("PATH", "")]))

    real = os.path.realpath(sys.executable)
    matches = [info for info in iter_interpreters(cache=session_cache) if os.path.realpath(info.executable) == real]
    assert len(matches) == 1


@pytest.mark.usefixtures("uv_dir")
def test_iter_interpreters_try_first_with_yields_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    session_cache: DiskCache,
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    results = list(iter_interpreters(try_first_with=[sys.executable], cache=session_cache))
    assert results
    assert os.path.realpath(results[0].executable) == os.path.realpath(sys.executable)


def test_iter_interpreters_skips_none_from_propose(
    session_cache: DiskCache,
    mocker: MockerFixture,
) -> None:
    real_info = PythonInfo.current(session_cache)
    mocker.patch(
        "python_discovery._discovery.propose_interpreters",
        return_value=iter([(None, True), (real_info, True)]),
    )
    results = list(iter_interpreters(cache=session_cache))
    assert results == [real_info]


def test_iter_interpreters_skips_when_no_executable(
    session_cache: DiskCache,
    mocker: MockerFixture,
) -> None:
    bogus = mocker.MagicMock(spec=PythonInfo)
    bogus.system_executable = None
    bogus.executable = None
    mocker.patch(
        "python_discovery._discovery.propose_interpreters",
        return_value=iter([(bogus, True)]),
    )
    assert list(iter_interpreters(cache=session_cache)) == []


def test_iter_interpreters_uv_yields_when_interrogation_succeeds(
    uv_dir: Path,
    session_cache: DiskCache,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
) -> None:
    monkeypatch.setenv("PATH", "")
    bin_path = uv_dir / "cpython-3.99-fake/bin"
    bin_path.mkdir(parents=True)
    (bin_path / "python").touch()

    fake_info = mocker.MagicMock(spec=PythonInfo)
    fake_info.system_executable = str(uv_dir / "fake-unique" / "python")
    fake_info.executable = fake_info.system_executable
    fake_info.satisfies.return_value = True
    mocker.patch("python_discovery._discovery.PathPythonInfo.from_exe", return_value=fake_info)

    assert fake_info in list(iter_interpreters(cache=session_cache))


@pytest.mark.parametrize(
    ("real_files", "symlinks", "expected_real"),
    [
        pytest.param(
            ("pypy-3.10-linux-x86_64-gnu/bin/pypy3.10",),
            (
                ("pypy-3.10-linux-x86_64-gnu/bin/python", "pypy-3.10-linux-x86_64-gnu/bin/pypy3.10"),
                ("pypy-3.10-linux-x86_64-gnu/bin/pypy", "pypy-3.10-linux-x86_64-gnu/bin/pypy3.10"),
            ),
            ("pypy-3.10-linux-x86_64-gnu/bin/pypy3.10",),
            id="pypy-unix-with-python-symlink",
        ),
        pytest.param(
            ("graalpy-24.1.1-linux-x86_64-gnu/bin/graalpy",),
            (),
            ("graalpy-24.1.1-linux-x86_64-gnu/bin/graalpy",),
            id="graalpy-unix",
        ),
        pytest.param(
            (
                "cpython-3.14.4-windows-x86_64-none/python.exe",
                "pypy-3.11.15-windows-x86_64-none/pypy3.11.exe",
                "graalpy-3.11-windows-x86_64-none/bin/graalpy.exe",
            ),
            (),
            (
                "cpython-3.14.4-windows-x86_64-none/python.exe",
                "pypy-3.11.15-windows-x86_64-none/pypy3.11.exe",
                "graalpy-3.11-windows-x86_64-none/bin/graalpy.exe",
            ),
            id="windows-all-impls",
        ),
    ],
)
def test_iter_interpreters_uv_layout(
    uv_dir: Path,
    session_cache: DiskCache,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
    real_files: tuple[str, ...],
    symlinks: tuple[tuple[str, str], ...],
    expected_real: tuple[str, ...],
) -> None:
    monkeypatch.setenv("PATH", "")
    for rel in real_files:
        path = uv_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    for link_rel, target_rel in symlinks:
        Path(str(uv_dir / link_rel)).symlink_to(uv_dir / target_rel)

    mock_from_exe = mocker.patch("python_discovery._discovery.PathPythonInfo.from_exe", return_value=None)
    list(iter_interpreters(cache=session_cache))

    interrogated_real = {os.path.realpath(call.args[0]) for call in mock_from_exe.call_args_list}
    assert interrogated_real == {os.path.realpath(uv_dir / r) for r in expected_real}


@pytest.mark.parametrize(
    ("planted", "key", "expected"),
    [
        pytest.param(
            (
                "pypy-3.8.16-macos-aarch64-none/bin/python",
                "graalpy-3.8.0-macos-aarch64-none/bin/python",
                "cpython-3.8.20-macos-aarch64-none/bin/python",
            ),
            "3.8",
            ["cpython-3.8.20-macos-aarch64-none/bin/python"],
            id="bare-version-skips-alternative-implementations",
        ),
        pytest.param(
            ("cpython-3.8.20-macos-aarch64-none/bin/python", "pypy-3.8.16-macos-aarch64-none/bin/pypy3.8"),
            "pypy3.8",
            ["pypy-3.8.16-macos-aarch64-none/bin/pypy3.8"],
            id="implementation-spec-reaches-pypy",
        ),
        pytest.param(
            (
                "cpython-3.8.2-macos-aarch64-none/bin/python",
                "cpython-3.8.20-macos-aarch64-none/bin/python",
                "cpython-3.8.10-macos-aarch64-none/bin/python",
            ),
            "3.8",
            [
                "cpython-3.8.20-macos-aarch64-none/bin/python",
                "cpython-3.8.10-macos-aarch64-none/bin/python",
                "cpython-3.8.2-macos-aarch64-none/bin/python",
            ],
            id="newest-version-first",
        ),
        pytest.param(
            ("cpython-3.15.0b3-macos-aarch64-none/bin/python", "cpython-3.15.0-macos-aarch64-none/bin/python"),
            "3.15",
            [
                "cpython-3.15.0-macos-aarch64-none/bin/python",
                "cpython-3.15.0b3-macos-aarch64-none/bin/python",
            ],
            id="final-release-before-prerelease",
        ),
        pytest.param(
            ("cpython-3.8.20-macos-aarch64-none/bin/python", "cpython-3.12.13-macos-aarch64-none/bin/python"),
            "3.12",
            ["cpython-3.12.13-macos-aarch64-none/bin/python"],
            id="version-rules-out-the-rest",
        ),
        pytest.param(
            ("cpython-3.8.20-macos-aarch64-none/bin/python", "cpython-3.12.13-macos-aarch64-none/bin/python"),
            ">=3.12",
            ["cpython-3.12.13-macos-aarch64-none/bin/python"],
            id="specifier-rules-out-the-rest",
        ),
        pytest.param(
            (
                "cpython-3.14.6-macos-aarch64-none/bin/python",
                "cpython-3.14.6+freethreaded-macos-aarch64-none/bin/python",
            ),
            "3.14t",
            ["cpython-3.14.6+freethreaded-macos-aarch64-none/bin/python"],
            id="t-suffix-wants-freethreaded",
        ),
        pytest.param(
            (
                "cpython-3.14.6-macos-aarch64-none/bin/python",
                "cpython-3.14.6+debug-macos-aarch64-none/bin/python",
                "cpython-3.14.6+freethreaded+debug-macos-aarch64-none/bin/python",
            ),
            "3.14d",
            ["cpython-3.14.6+debug-macos-aarch64-none/bin/python"],
            id="d-suffix-wants-debug",
        ),
        pytest.param(
            (
                "cpython-3.14.6-macos-aarch64-none/bin/python",
                "cpython-3.14.6+debug-macos-aarch64-none/bin/python",
                "cpython-3.14.6+freethreaded+debug-macos-aarch64-none/bin/python",
            ),
            "3.14-dbg",
            ["cpython-3.14.6+debug-macos-aarch64-none/bin/python"],
            id="dbg-suffix-wants-debug",
        ),
        # a spec silent about `Py_DEBUG` leaves debug builds reachable, ranked behind the default build
        pytest.param(
            (
                "cpython-3.14.6+debug-macos-aarch64-none/bin/python",
                "cpython-3.14.6-macos-aarch64-none/bin/python",
            ),
            "3.14",
            [
                "cpython-3.14.6-macos-aarch64-none/bin/python",
                "cpython-3.14.6+debug-macos-aarch64-none/bin/python",
            ],
            id="unconstrained-debug-ranks-second",
        ),
        # older uv releases name GraalPy installs after the GraalVM version, not the Python one
        pytest.param(
            ("graalpy-24.1.1-linux-x86_64-gnu/bin/graalpy",),
            "graalpy3.11",
            ["graalpy-24.1.1-linux-x86_64-gnu/bin/graalpy"],
            id="graalpy-key-version-does-not-filter",
        ),
        pytest.param(
            ("a-hand-made-store/bin/python", "cpython-3.8.20-macos-aarch64-none/bin/python"),
            "3.8",
            ["cpython-3.8.20-macos-aarch64-none/bin/python", "a-hand-made-store/bin/python"],
            id="unrecognized-directory-probed-last",
        ),
        pytest.param(
            (".temp/bin/python", ".lock", "README", "cpython-3.8.20-macos-aarch64-none/bin/python"),
            "3.8",
            ["cpython-3.8.20-macos-aarch64-none/bin/python"],
            id="bookkeeping-entries-skipped",
        ),
        pytest.param(
            ("cpython-3.8.20-macos-aarch64-none/install/bin/python",),
            "3.8",
            ["cpython-3.8.20-macos-aarch64-none/install/bin/python"],
            id="install-subdirectory-layout",
        ),
        pytest.param(
            (
                "pyston-3.8.12-linux-x86_64-gnu/bin/python",
                "graalpy-24.1.1-linux-x86_64-gnu/bin/graalpy",
                "pypy-3.11.15-linux-x86_64-gnu/bin/pypy3.11",
                "cpython-3.12.13-linux-x86_64-gnu/bin/python",
            ),
            None,
            [
                "cpython-3.12.13-linux-x86_64-gnu/bin/python",
                "pypy-3.11.15-linux-x86_64-gnu/bin/pypy3.11",
                "graalpy-24.1.1-linux-x86_64-gnu/bin/graalpy",
                "pyston-3.8.12-linux-x86_64-gnu/bin/python",
            ],
            id="enumeration-orders-implementations",
        ),
    ],
)
def test_iter_interpreters_uv_probe_order(
    uv_install: Callable[..., None],
    uv_probed: Callable[[str | None], list[str]],
    planted: tuple[str, ...],
    key: str | None,
    expected: list[str],
) -> None:
    uv_install(*planted)

    assert uv_probed(key) == expected


def test_iter_interpreters_uv_minor_version_link_loses_to_its_target(
    uv_dir: Path, uv_install: Callable[..., None], uv_probed: Callable[[str | None], list[str]]
) -> None:
    """uv links `cpython-3.15` at the concrete install, and repoints it on the next patch release."""
    uv_install("cpython-3.15.0b3-macos-aarch64-none/bin/python")
    Path(uv_dir / "cpython-3.15-macos-aarch64-none").symlink_to(uv_dir / "cpython-3.15.0b3-macos-aarch64-none")

    assert uv_probed("3.15") == ["cpython-3.15.0b3-macos-aarch64-none/bin/python"]


def test_iter_interpreters_uv_probes_one_executable_per_install(
    uv_dir: Path, uv_install: Callable[..., None], monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
) -> None:
    """GraalPy ships bin/python as a copy of bin/graalpy, so the realpath dedup alone would spawn it twice."""
    monkeypatch.setenv("PATH", "")
    uv_install("graalpy-3.11.0-macos-aarch64-none/bin/python", "graalpy-3.11.0-macos-aarch64-none/bin/graalpy")
    executable = str(uv_dir / "graalpy-3.11.0-macos-aarch64-none" / "bin" / "python")
    from_exe = mocker.patch(
        "python_discovery._discovery.PathPythonInfo.from_exe",
        return_value=mocker.create_autospec(
            PythonInfo, instance=True, system_executable=executable, executable=executable
        ),
    )

    list(iter_interpreters("graalpy3.11"))

    assert [call.args[0] for call in from_exe.call_args_list] == [executable]
