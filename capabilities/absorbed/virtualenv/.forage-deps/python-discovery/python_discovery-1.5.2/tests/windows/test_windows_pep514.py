from __future__ import annotations

import sys
import textwrap

import pytest


@pytest.mark.usefixtures("_mock_registry")
def test_pep514_discovers_interpreters() -> None:
    from python_discovery._windows._pep514 import discover_pythons

    interpreters = list(discover_pythons())
    assert len(interpreters) == 12
    companies = {i[0] for i in interpreters}
    assert "ContinuumAnalytics" in companies
    assert "PythonCore" in companies
    assert "CompanyA" in companies


@pytest.mark.usefixtures("_mock_registry")
def test_pep514_parse_functions() -> None:
    from python_discovery._windows._pep514 import parse_arch, parse_version

    assert parse_arch("64bit") == 64
    assert parse_arch("32bit") == 32
    with pytest.raises(ValueError, match="invalid format"):
        parse_arch("magic")
    with pytest.raises(ValueError, match="arch is not string"):
        parse_arch(100)

    assert parse_version("3.12") == (3, 12, None)
    assert parse_version("3.12.1") == (3, 12, 1)
    assert parse_version("3") == (3, None, None)
    with pytest.raises(ValueError, match="invalid format"):
        parse_version("3.X")
    with pytest.raises(ValueError, match="version is not string"):
        parse_version(2778)


@pytest.mark.skipif(sys.platform != "win32", reason="path joining differs on POSIX")
@pytest.mark.usefixtures("_mock_registry")
def test_pep514() -> None:
    from python_discovery._windows._pep514 import discover_pythons

    interpreters = list(discover_pythons())
    assert interpreters == [
        ("ContinuumAnalytics", 3, 10, 32, False, "C:\\Users\\user\\Miniconda3\\python.exe", None),
        ("ContinuumAnalytics", 3, 10, 64, False, "C:\\Users\\user\\Miniconda3-64\\python.exe", None),
        (
            "PythonCore",
            3,
            9,
            64,
            False,
            "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python39\\python.exe",
            None,
        ),
        (
            "PythonCore",
            3,
            9,
            64,
            False,
            "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python39\\python.exe",
            None,
        ),
        (
            "PythonCore",
            3,
            8,
            64,
            False,
            "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python38\\python.exe",
            None,
        ),
        (
            "PythonCore",
            3,
            9,
            64,
            False,
            "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python39\\python.exe",
            None,
        ),
        (
            "PythonCore",
            3,
            10,
            32,
            False,
            "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python310-32\\python.exe",
            None,
        ),
        (
            "PythonCore",
            3,
            12,
            64,
            False,
            "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python312\\python.exe",
            None,
        ),
        (
            "PythonCore",
            3,
            13,
            64,
            True,
            "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python313\\python3.13t.exe",
            None,
        ),
        ("CompanyA", 3, 6, 64, False, "Z:\\CompanyA\\Python\\3.6\\python.exe", None),
        ("PythonCore", 2, 7, 64, False, "C:\\Python27\\python.exe", None),
        ("PythonCore", 3, 7, 64, False, "C:\\Python37\\python.exe", None),
    ]


@pytest.mark.skipif(sys.platform != "win32", reason="path joining differs on POSIX")
@pytest.mark.usefixtures("_mock_registry")
def test_pep514_run(capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture) -> None:
    from python_discovery._windows import _pep514 as pep514

    pep514._run()
    out, err = capsys.readouterr()
    py = r"C:\Users\user\AppData\Local\Programs\Python"
    expected = textwrap.dedent(
        rf"""
    ('CompanyA', 3, 6, 64, False, 'Z:\\CompanyA\\Python\\3.6\\python.exe', None)
    ('ContinuumAnalytics', 3, 10, 32, False, 'C:\\Users\\user\\Miniconda3\\python.exe', None)
    ('ContinuumAnalytics', 3, 10, 64, False, 'C:\\Users\\user\\Miniconda3-64\\python.exe', None)
    ('PythonCore', 2, 7, 64, False, 'C:\\Python27\\python.exe', None)
    ('PythonCore', 3, 10, 32, False, '{py}\\Python310-32\\python.exe', None)
    ('PythonCore', 3, 12, 64, False, '{py}\\Python312\\python.exe', None)
    ('PythonCore', 3, 13, 64, True, '{py}\\Python313\\python3.13t.exe', None)
    ('PythonCore', 3, 7, 64, False, 'C:\\Python37\\python.exe', None)
    ('PythonCore', 3, 8, 64, False, '{py}\\Python38\\python.exe', None)
    ('PythonCore', 3, 9, 64, False, '{py}\\Python39\\python.exe', None)
    ('PythonCore', 3, 9, 64, False, '{py}\\Python39\\python.exe', None)
    ('PythonCore', 3, 9, 64, False, '{py}\\Python39\\python.exe', None)
    """,
    ).strip()
    assert out.strip() == expected
    assert not err
    prefix = "PEP-514 violation in Windows Registry at "
    expected_logs = [
        f"{prefix}HKEY_CURRENT_USER/PythonCore/3.1/SysArchitecture error: invalid format magic",
        f"{prefix}HKEY_CURRENT_USER/PythonCore/3.2/SysArchitecture error: arch is not string: 100",
        f"{prefix}HKEY_CURRENT_USER/PythonCore/3.3 error: no ExecutablePath or default for it",
        f"{prefix}HKEY_CURRENT_USER/PythonCore/3.3 error: could not load exe with value None",
        f"{prefix}HKEY_CURRENT_USER/PythonCore/3.11/InstallPath error: missing",
        f"{prefix}HKEY_CURRENT_USER/PythonCore/3.12/SysVersion error: invalid format magic",
        f"{prefix}HKEY_CURRENT_USER/PythonCore/3.X/SysVersion error: version is not string: 2778",
        f"{prefix}HKEY_CURRENT_USER/PythonCore/3.X error: invalid format 3.X",
    ]
    assert caplog.messages == expected_logs
