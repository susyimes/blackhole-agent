"""Serialize short updates across processes without locking the file being replaced."""

import errno
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

if os.name == "nt":
    import msvcrt
else:
    import fcntl


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
