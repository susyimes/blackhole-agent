"""Durable-state overlay: keep the committed checkout byte-stable under tests.

The capability ledger, synthesized steps, and artifact trees are git-tracked
durable state. Historically any caller that passed the real repository root to
a compounder plane, proof, or CLI invocation persisted straight into the
tracked files, so a plain ``pytest`` run rewrote ``capabilities/ledger.json``
and left the worktree dirty.

When ``BLACKHOLE_DURABLE_ROOT`` is set (the test suite sets it to a per-session
temporary directory), writes that target paths inside a Git worktree are
redirected into the overlay root while preserving their layout relative to the
worktree root. Reads fall through to the real path when no overlay copy
exists, so read-only callers still see committed state while writers can never
dirty the checkout.

The variable is read live on every call; nothing is cached at import time, so
subprocesses inherit the overlay through the environment and callers may
enable or disable it at any point. When the variable is unset the overlay is
fully inert: production controller and milestone-acceptance writes keep
landing in the real ledger.
"""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

OVERLAY_ENV = "BLACKHOLE_DURABLE_ROOT"


@contextmanager
def durable_overlay_session(root: Path | None = None) -> Iterator[Path | None]:
    """Activate the overlay for the duration of the block.

    Used by read-only verification flows (for example ``capability audit``):
    the proofs they replay may persist bundles, certificates, or ledger
    stamps, and verification must not dirty the checkout it verifies. When
    the overlay is already active the block is a no-op passthrough yielding
    the existing root; otherwise a fresh temporary overlay is installed and
    removed on exit. Subprocesses spawned inside the block inherit the
    variable through the environment.
    """

    existing = overlay_root()
    if existing is not None:
        yield existing
        return
    if root is not None:
        previous = os.environ.get(OVERLAY_ENV)
        os.environ[OVERLAY_ENV] = str(root)
        try:
            yield root
        finally:
            if previous is None:
                os.environ.pop(OVERLAY_ENV, None)
            else:
                os.environ[OVERLAY_ENV] = previous
        return
    with tempfile.TemporaryDirectory(prefix="blackhole-durable-overlay-") as tmp:
        previous = os.environ.get(OVERLAY_ENV)
        os.environ[OVERLAY_ENV] = tmp
        try:
            yield Path(tmp)
        finally:
            if previous is None:
                os.environ.pop(OVERLAY_ENV, None)
            else:
                os.environ[OVERLAY_ENV] = previous


def overlay_root() -> Path | None:
    """Return the active overlay root, or ``None`` when the overlay is off."""

    raw = os.environ.get(OVERLAY_ENV, "").strip()
    if not raw:
        return None
    return Path(raw).resolve()


def _worktree_root(path: Path) -> Path | None:
    """Return the enclosing Git worktree root for ``path``, if any.

    A linked worktree has a ``.git`` file instead of a directory, so existence
    is checked rather than directory-ness. ``path`` may not exist yet; the
    walk starts at its parent in that case.
    """

    start = path if path.is_dir() else path.parent
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _tombstone_path(overlay_path: Path) -> Path:
    return overlay_path.with_suffix(overlay_path.suffix + ".deleted")


def durable_write_path(path: Path | str) -> Path:
    """Map a write target into the overlay when it lives inside a worktree.

    Paths outside any Git worktree (for example ``tmp_path`` fixtures) are
    returned unchanged, as are all paths while the overlay is disabled. When a
    tombstone from :func:`durable_forget` covers the target, it is cleared: the
    caller is about to create the file, so the deletion mask must not hide it.
    """

    target = Path(path)
    root = overlay_root()
    if root is None:
        return target
    resolved = target.resolve()
    base = _worktree_root(resolved)
    if base is None:
        return target
    try:
        relative = resolved.relative_to(base)
    except ValueError:
        return target
    overlay_path = root / relative
    tombstone = _tombstone_path(overlay_path)
    if tombstone.exists():
        tombstone.unlink()
    return overlay_path


def durable_read_path(path: Path | str) -> Path:
    """Return the path a reader should open: overlay copy when present.

    Read-through keeps callers consistent: once a writer redirected a durable
    file into the overlay, later reads of the same real path observe the
    overlay copy instead of the stale committed file. A tombstoned path
    resolves to the (nonexistent) overlay location, so existence checks report
    it as deleted without touching the committed file.
    """

    target = Path(path)
    root = overlay_root()
    if root is None:
        return target
    resolved = target.resolve()
    base = _worktree_root(resolved)
    if base is None:
        return target
    try:
        relative = resolved.relative_to(base)
    except ValueError:
        return target
    overlay_path = root / relative
    if overlay_path.exists() or _tombstone_path(overlay_path).exists():
        return overlay_path
    return target


def durable_forget(path: Path | str) -> None:
    """Mask a durable path as deleted without touching the real file.

    Tests and sandbox flows need a "file absent" starting state for tracked
    artifact fixtures. With the overlay active this removes any overlay copy
    and records a tombstone; readers observe the file as gone while the
    committed file stays byte-identical. Outside a worktree, or with the
    overlay disabled, this behaves like a plain best-effort unlink.
    """

    target = Path(path)
    root = overlay_root()
    if root is None:
        target.unlink(missing_ok=True)
        return
    resolved = target.resolve()
    base = _worktree_root(resolved)
    if base is None:
        target.unlink(missing_ok=True)
        return
    try:
        relative = resolved.relative_to(base)
    except ValueError:
        target.unlink(missing_ok=True)
        return
    overlay_path = root / relative
    overlay_path.unlink(missing_ok=True)
    tombstone = _tombstone_path(overlay_path)
    tombstone.parent.mkdir(parents=True, exist_ok=True)
    tombstone.write_text("deleted\n", encoding="utf-8")
