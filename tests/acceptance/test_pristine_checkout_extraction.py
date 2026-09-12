"""Materialize a real committed repository with Unicode and deep asset paths.

The same public checkout operation runs against baseline and candidate src.
Missing files or a rejected checkout are unmet outcomes, never feature checks.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


def _native(path: Path) -> str:
    absolute = str(path.resolve())
    return "\\\\?\\" + absolute if os.name == "nt" else absolute


@contextmanager
def _fixture_directory():
    base = Path(tempfile.mkdtemp(prefix="accept-checkout-"))
    try:
        yield base
    finally:
        assert base.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve())

        def remove_readonly(function, path, _error):
            os.chmod(path, stat.S_IWRITE)
            function(path)

        shutil.rmtree(_native(base), onerror=remove_readonly)


def main() -> dict[str, object]:
    from blackhole_agent import capability_portability as portability

    observed: dict[str, object] = {"operation": "checkout_pristine_source"}
    with _fixture_directory() as base:
        repo = base / "repo"
        repo.mkdir()
        fixtures = {
            "src/package/__init__.py": b"NAME = 'checkout-fixture'\n",
            "tests/fixtures/static/\u2297.txt": b"unicode-sentinel\n",
            "capabilities/" + "/".join(["deepdir" * 5] * 6) + "/asset.js": b"deep-sentinel\n",
            "schemas/example.json": b"{}\n",
            "pyproject.toml": b"[project]\nname = 'checkout-fixture'\n",
        }
        for relative, payload in fixtures.items():
            path = repo / relative
            os.makedirs(_native(path.parent), exist_ok=True)
            with open(_native(path), "wb") as stream:
                stream.write(payload)

        def git(*args: str) -> None:
            subprocess.run(
                ["git", "-c", "core.longpaths=true", "-c", "core.autocrlf=false",
                 "-c", "user.name=Checkout Fixture", "-c", "user.email=fixture@localhost",
                 *args],
                cwd=repo, capture_output=True, check=True, timeout=30,
            )

        git("init", "-q")
        git("config", "core.autocrlf", "false")
        git("config", "core.longpaths", "true")
        git("add", ".")
        git("-c", "commit.gpgsign=false", "commit", "-qm", "checkout fixture")
        checkout = base / "checkout"
        completed = False
        with patch.object(portability, "REPO_ROOT", repo):
            try:
                report = portability.checkout_pristine_source(checkout)
                completed = True
                observed["file_count"] = report["file_count"]
            except (OSError, ValueError, subprocess.CalledProcessError) as error:
                observed["checkout_error"] = str(error)
                if isinstance(error, subprocess.CalledProcessError):
                    observed["stderr"] = (error.stderr or b"").decode("utf-8", errors="replace")[-1200:]

        matches: dict[str, bool] = {}
        mismatches: dict[str, str] = {}
        for relative, payload in fixtures.items():
            try:
                with open(_native(checkout / relative), "rb") as stream:
                    actual = stream.read()
                matches[relative] = actual == payload
                if actual != payload:
                    mismatches[relative] = repr(actual[:100])
            except OSError as error:
                matches[relative] = False
                mismatches[relative] = str(error)
        observed.update({
            "checkout_completed": completed,
            "fixture_matches": matches,
            "mismatches": mismatches,
            "longest_checkout_path": max(len(str(checkout / name)) for name in fixtures),
        })
        return {
            "passed": completed and all(matches.values()) and observed.get("file_count") == len(fixtures),
            "observed": observed,
        }


if __name__ == "__main__":
    print(json.dumps(main(), sort_keys=True))
