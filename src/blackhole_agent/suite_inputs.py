"""Identify the checkout bytes on which resumable pytest shards depend."""

import hashlib
import os
import stat
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterable, Iterator


_CACHE_DIRS = {".git", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".venv", "__pycache__"}


def _walk_error(error: OSError) -> None:
    raise error


def _project_files(root: Path) -> Iterator[Path]:
    if (root / ".git").exists():
        overrides = {"GIT_DIR", "GIT_COMMON_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"}
        names = subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", "."],
            cwd=root, env={k: v for k, v in os.environ.items() if k not in overrides},
            stderr=subprocess.PIPE, timeout=30,
        )
        yield from (Path(os.fsdecode(name)) for name in names.split(b"\0") if name)
        return
    # Standalone suites also run outside Git. Prune virtual environments and interpreter caches.
    for directory, dirs, files in os.walk(root, onerror=_walk_error):
        parent = Path(directory)
        if "pyvenv.cfg" in files:
            dirs.clear()
            continue
        dirs[:] = [name for name in dirs if name not in _CACHE_DIRS]
        for name in dirs:
            _check_directory(parent / name)
        for name in files:
            yield (parent / name).relative_to(root)


def _check_directory(path: Path) -> None:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise OSError(f"linked suite directory: {path}")


def file_digest(path: Path) -> bytes:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise OSError(f"unsupported suite input: {path}")
    digest = hashlib.sha256(stat.S_IMODE(info.st_mode).to_bytes(2, "big"))
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(256 * 1024), b""):
            digest.update(block)
    return digest.digest()


def inputs_digest(entries: Iterable[tuple[bytes, bytes]]) -> str:
    digest = hashlib.sha256()
    for name, content in sorted(entries):
        digest.update(name + b"\0" + len(content).to_bytes(2, "big") + content)
    return digest.hexdigest()


def suite_inputs(root: Path, ledger: Path) -> tuple[str, dict[Path, bytes]]:
    test_dir = root / "tests"
    if test_dir.exists():
        _check_directory(test_dir)
    tests = {p: file_digest(p) for p in test_dir.glob("test_*.py") if p.is_file()}
    if not tests:
        return inputs_digest(()), tests
    excluded = {ledger, ledger.with_name(ledger.name + ".guard"), *tests}
    paths = set()
    for path in _project_files(root):
        if path.suffix in {".pyc", ".pyo"} or _CACHE_DIRS.intersection(path.parts) or root / path in excluded:
            continue
        if root / path.parent == ledger.parent and path.suffix == ".tmp" and path.name.startswith(f".{ledger.name}-"):
            continue
        paths.add(path)
    parents = {path.parent for path in paths}
    for parent in sorted(parents | {p for directory in parents for p in directory.parents}):
        try:
            _check_directory(root / parent)
        except (FileNotFoundError, NotADirectoryError):
            pass  # A tracked subtree can be absent from the working tree.

    def read_batch(batch: list[Path]) -> list[tuple[bytes, bytes]]:
        entries = []
        for path in batch:
            try:
                entries.append((os.fsencode(path.as_posix()), file_digest(root / path)))
            except (FileNotFoundError, NotADirectoryError):
                continue
        return entries

    # Bound outstanding I/O jobs on checkouts with tens of thousands of files.
    ordered = sorted(paths)
    batches = (ordered[i:i + 256] for i in range(0, len(ordered), 256))
    with ThreadPoolExecutor(max_workers=8) as pool:
        shared = inputs_digest(entry for batch in pool.map(read_batch, batches) for entry in batch)
    return shared, tests
