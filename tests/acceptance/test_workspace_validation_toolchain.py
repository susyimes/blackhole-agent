"""Replay an invoice check with a second project's Python, uv target and import path active."""

import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from blackhole_agent.unbound import replay_validation_command, reproduce_validation
from blackhole_agent.validation_env import venv_python


def prices(rate):
    return (
        "import sys\n"
        f"def quote(units): return units * {rate}\n"
        "def main(): print(quote(int(sys.argv[1])))\n"
    )


def project(root, version, rate):
    root.mkdir()
    wheel = root / f"invoice_tool-{version}-py3-none-any.whl"
    info = f"invoice_tool-{version}.dist-info"
    files = {
        "price_book.py": prices(rate),
        # This offline wheel also supplies the three imports checked by environment repair.
        "pytest.py": "", "ruff.py": "", "yaml.py": "",
        f"{info}/METADATA": f"Metadata-Version: 2.1\nName: invoice-tool\nVersion: {version}\n",
        f"{info}/WHEEL": "Wheel-Version: 1.0\nGenerator: fixture\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        f"{info}/entry_points.txt": "[console_scripts]\nquote-order = price_book:main\n",
    }
    with ZipFile(wheel, "w") as archive:
        rows = []
        for name, value in files.items():
            data = value.encode()
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
            rows.append(f"{name},sha256={digest},{len(data)}")
            archive.writestr(name, data)
        record = f"{info}/RECORD"
        archive.writestr(record, "\n".join([*rows, record + ",,", ""]))
    (root / "pyproject.toml").write_text(
        '[project]\nname = "checkout"\nversion = "1"\nrequires-python = ">=3.10"\n'
        f'[project.optional-dependencies]\ndev = ["invoice-tool @ {wheel.as_uri()}"]\n',
        encoding="utf-8",
    )
    return root


def installed_quote(root):
    python = venv_python(root)
    if not python.is_file():
        return None
    run = subprocess.run(
        [python, "-I", "-c", "from price_book import quote; print(quote(5))"],
        capture_output=True, text=True, timeout=10,
    )
    return int(run.stdout) if run.returncode == 0 else None


def observe(root):
    peer = project(root / "other project", "1.0", 7)
    workspace = project(root / "mission project", "2.0", 13)
    peer_env = peer / ".venv"
    env = {
        "UV_OFFLINE": "1", "UV_CACHE_DIR": str(root / "cache"), "UV_PYTHON": sys.executable,
        "UV_PYTHON_DOWNLOADS": "never", "UV_PROJECT_ENVIRONMENT": str(peer_env),
        "UV_PROJECT": str(workspace), "UV_WORKING_DIR": str(workspace),
    }
    with patch.dict(os.environ, env):
        subprocess.run(
            ["uv", "sync", "--project", str(peer), "--extra", "dev"], cwd=peer,
            capture_output=True, check=True, timeout=30,
        )
        before = installed_quote(peer)
        shadow = root / "shadow"
        shadow.mkdir()
        (shadow / "price_book.py").write_text(prices(17), encoding="utf-8")
        (workspace / "check.py").write_text(
            "import subprocess, sys\nfrom pathlib import Path\nfrom price_book import quote\n"
            "totals = [quote(5), int(subprocess.check_output(['quote-order', '5']))]\n"
            "local = Path(sys.prefix).resolve() == (Path.cwd() / '.venv').resolve()\n"
            "print(*totals, 'mission' if local else 'foreign')\n"
            "raise SystemExit(0 if totals == [int(sys.argv[1])] * 2 else 23)\n",
            encoding="utf-8",
        )
        commands = ("python check.py 65", "python check.py 85", f'PYTHONPATH="{shadow}" python check.py 85')
        peer_path = str(venv_python(peer).parent) + os.pathsep + os.environ["PATH"]
        with patch.dict(os.environ, VIRTUAL_ENV=str(peer_env), PYTHONPATH=str(shadow), PATH=peer_path):
            receipts = reproduce_validation(workspace, tuple({"command": cmd, "exit_code": 0} for cmd in commands))
            with patch.dict(os.environ, UV_PROJECT=str(peer), UV_WORKING_DIR=str(peer)):
                uv_checks = [replay_validation_command(workspace, command) for command in (
                    "uv run --no-sync quote-order 5", f'uv run --no-sync --project "{peer}" quote-order 5',
                )]
        return {
            "other_project_before_after": [before, installed_quote(peer)],
            "installed_in_mission": installed_quote(workspace),
            "checks": [[r["reproduced_exit_code"], r["stdout_tail"].strip()] for r in receipts],
            "uv_default_and_explicit_project": [[r["reproduced_exit_code"], r["stdout_tail"].strip()] for r in uv_checks],
        }


EXPECTED = {
    "other_project_before_after": [35, 35], "installed_in_mission": 65,
    "checks": [[0, "65 65 mission"], [23, "65 65 mission"], [0, "85 85 mission"]],
    "uv_default_and_explicit_project": [[0, "65"], [0, "35"]],
}


def test_workspace_validation_toolchain(tmp_path):
    assert observe(tmp_path) == EXPECTED


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="bh-validation-") as directory:
        try:
            observed = observe(Path(directory).resolve())
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            observed = {"error": str(error), "stderr": str(getattr(error, "stderr", ""))[-800:]}
        print(json.dumps({"passed": observed == EXPECTED, "observed": observed}))
