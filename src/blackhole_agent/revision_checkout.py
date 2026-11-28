"""Read selected checkout bytes from a commit using a private Git index."""

import os
import subprocess
from collections.abc import Callable, Iterable
from pathlib import Path


class RevisionCheckout:
    """The caller owns the empty scratch directory and its lifetime."""

    def __init__(self, repo: Path, commit: str, scratch: Path, command_runner: Callable = subprocess.run) -> None:
        scratch = scratch.absolute()
        self._runner = command_runner
        location = command_runner(
            ["git", "rev-parse", "--absolute-git-dir"], cwd=repo, capture_output=True, check=True, timeout=120,
        )
        self._tree = scratch / "empty"
        self._tree.mkdir()
        self._env = {
            **os.environ, "GIT_DIR": os.fsdecode(location.stdout.removesuffix(b"\n")),
            "GIT_INDEX_FILE": str(scratch / "index"), "GIT_ATTR_SOURCE": commit,
        }
        self._options = [
            "git", "-c", f"core.hooksPath={scratch / 'hooks'}",
            "-c", "core.splitIndex=false", "-c", "core.fsmonitor=false",
        ]
        # A snapshot may apply Git's built-in conversions but cannot run a smudge program.
        keys = self.git("config", "--null", "--name-only", "--list").split(b"\0")
        drivers = {
            os.fsdecode(key.rsplit(b".", 1)[0]) for key in keys
            if key.startswith(b"filter.") and key.endswith((b".smudge", b".process"))
        }
        for driver in drivers:
            if "=" in driver:
                raise ValueError("unsupported Git filter name")
            for setting in ("process=", "smudge=", "required=true"):
                self._options.extend(["-c", f"{driver}.{setting}"])
        self.git("read-tree", "--no-sparse-checkout", commit)

    def git(self, *args: str, paths: Iterable[bytes] = (), tree: Path | None = None) -> bytes:
        cwd = tree or self._tree
        return self._runner(
            [*self._options, f"--work-tree={cwd.absolute()}", *args], cwd=cwd, env=self._env,
            input=b"".join(name + b"\0" for name in paths), capture_output=True, check=True, timeout=120,
        ).stdout

    def modes(self, *paths: str) -> dict[bytes, bytes]:
        modes = {}
        for entry in self.git("--literal-pathspecs", "ls-files", "--stage", "-z", "--", *paths).split(b"\0")[:-1]:
            meta, name = entry.split(b"\t", 1)
            modes[name] = meta.split()[0]
        return modes

    def write(self, destination: Path, paths: Iterable[bytes]) -> None:
        self.git("checkout-index", f"--prefix={destination.absolute().as_posix()}/", "-z", "--stdin", paths=paths)
