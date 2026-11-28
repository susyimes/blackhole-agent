"""Publish one poll under its cursor lock. Prepared files stay on their destination volumes."""

import hashlib
import json
import os
from itertools import count
from pathlib import Path
from uuid import UUID, uuid4, uuid5

from blackhole_agent.file_guard import atomic_write_json, replace_file


def next_digest_archive(output_dir: Path, timestamp: str) -> tuple[Path, str]:
    """Keep earlier archives when the wall clock repeats during a retry."""
    for sequence in count(1):
        suffix = "" if sequence == 1 else f"_{sequence:04d}"
        path = output_dir / f"github-growth-digest-{timestamp}{suffix}.json"
        if not os.path.lexists(path) and not os.path.lexists(path.with_suffix(".md")):
            return path, suffix


def _journal(cursor: Path) -> Path:
    return cursor.with_name(f".{cursor.name}.intake.json")


def _draft(destination: Path, generation: UUID) -> Path:
    return destination.with_name(f".intake-{uuid5(generation, destination.name).hex}.tmp")


def recover_intake_batch(cursor: Path) -> None:
    journal = _journal(cursor)
    try:
        record = json.loads(journal.read_bytes())
    except FileNotFoundError:
        return
    generation = UUID(record["generation"])
    targets = [Path(path) for path in record["targets"]]
    if record["phase"] == "staging":
        # No public file can have changed before all drafts were closed.
        for path in targets:
            draft = _draft(path, generation)
            if draft.exists():
                draft.unlink()
    elif record["phase"] == "prepared":
        remaining = []
        for path, digest in zip(targets, record["digests"], strict=True):
            draft = _draft(path, generation)
            present = draft.exists()
            content = draft if present else path  # An earlier rename may have already delivered it.
            if hashlib.sha256(content.read_bytes()).hexdigest() != digest:
                raise RuntimeError(f"Intake batch content changed at {content}")
            if present:
                remaining.append((draft, path))
        for draft, path in remaining:
            replace_file(draft, path)
    else:
        raise ValueError(f"Unknown intake publication phase in {journal}")
    journal.unlink()


def publish_intake_batch(cursor: Path, files: list[tuple[Path, str]]) -> None:
    journal = _journal(cursor)
    generation = uuid4()
    # Resolve the parent, preserving replacement semantics for a symlink at the destination itself.
    targets = [path.parent.resolve() / path.name for path, _ in files]
    reserved = {cursor.parent.resolve() / name for name in (journal.name, cursor.name + ".guard")}
    locations = reserved.union(targets)
    if len(locations) != len(targets) + len(reserved) or any(locations.intersection(p.parents) for p in targets):
        raise ValueError("Intake outputs must have distinct file destinations")
    for path in targets:
        if path.is_dir() and not path.is_symlink():
            raise IsADirectoryError(str(path))
    record = {"generation": generation.hex, "targets": [str(path) for path in targets], "phase": "staging"}
    atomic_write_json(journal, record)
    digests = []
    for path, (_, text) in zip(targets, files):
        path.parent.mkdir(parents=True, exist_ok=True)
        data = text.replace("\n", os.linesep).encode("utf-8")
        with _draft(path, generation).open("xb") as stream:
            stream.write(data)
        digests.append(hashlib.sha256(data).hexdigest())
    atomic_write_json(journal, {**record, "phase": "prepared", "digests": digests})
    for path in targets:
        replace_file(_draft(path, generation), path)
    journal.unlink()
