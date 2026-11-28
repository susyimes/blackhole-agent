"""Serialize short updates across processes without locking the file being replaced."""

import errno
import json
import os
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

if os.name == "nt":
    import msvcrt
else:
    import fcntl


def json_text(payload: dict[str, Any], *, ensure_ascii: bool = False) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=ensure_ascii) + "\n"


def atomic_write_json(path: Path, payload: dict[str, Any], *, ensure_ascii: bool = False) -> None:
    atomic_write_text(path, json_text(payload, ensure_ascii=ensure_ascii))


def replace_file(source: Path, destination: Path) -> None:
    """Atomically install a sibling file, allowing brief Windows reader locks."""
    for attempt in range(8):
        try:
            os.replace(source, destination)
            return
        except OSError as error:
            if getattr(error, "winerror", None) not in {5, 32} or attempt == 7:
                raise
            time.sleep(0.01 * (attempt + 1))


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}-{uuid4().hex}.tmp")
    stream = temporary.open("x", encoding="utf-8")
    try:
        with stream:
            stream.write(text)
        replace_file(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def file_guard(path: Path, *, timeout: float | None = None, busy_message: str = "") -> Iterator[None]:
    """Keep the sidecar inode stable. Closing its handle releases the OS lock, including on process exit."""
    deadline = None if timeout is None else time.monotonic() + timeout
    with path.with_name(path.name + ".guard").open("a+b") as guard:
        guard.seek(0)
        while True:
            try:
                if os.name == "nt":
                    msvcrt.locking(guard.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(guard.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as error:
                if error.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                    raise
                if deadline is not None and time.monotonic() >= deadline:
                    if busy_message:
                        raise RuntimeError(busy_message) from error
                    raise
                time.sleep(0.01)
        # Older loop controllers expect the locked byte to exist before they open the guard.
        if guard.seek(0, os.SEEK_END) == 0:
            guard.write(b"\0")
            guard.flush()
        yield


def try_file_guard(path: Path) -> ExitStack | None:
    """Return a transferable guard, or None if another worker owns the file."""
    lease = ExitStack()
    try:
        lease.enter_context(file_guard(path, timeout=0, busy_message="file already owned"))
    except RuntimeError:
        return None
    return lease
