"""Preserve and serve files an untrusted tool wrote into per-invocation TEMP.

``POST /invoke`` already size-caps child-created scratch, then deletes the
directory. A capability that writes a report, image, or other declared file
therefore cannot be retrieved by an HTTP client. This module keeps those
files under a per-invocation directory and serves them:

- ``prepare_artifact_dir`` allocates ``.blackhole-agent/invocation-artifacts/<id>/``
- ``list_artifact_files`` returns the relative names and sizes that landed
- ``read_invocation_artifact`` returns file bytes after a fail-closed path
  check (no ``..``, no absolute names, no escape from the invocation dir)
- ``serve_invocation_artifact`` is the live-plane GET dispatcher so a
  missing module on a baseline tree is a clean ``passed=false`` rather than
  a crash

Honesty boundary: only regular files copied out of this invocation's TEMP
are served. Symlinks are skipped at harvest. The store does not expire;
operators delete the workspace root to drop artifacts, matching receipts.
"""

from __future__ import annotations

import json
import mimetypes
import re
import uuid
from pathlib import Path
from typing import Any

ARTIFACTS_RELATIVE = Path(".blackhole-agent") / "invocation-artifacts"
INVOCATION_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,128}\Z")
MAX_ARTIFACT_FILES = 256


class ArtifactError(Exception):
    """Fail-closed artifact refusal with an HTTP status."""

    def __init__(self, status: int, error: str) -> None:
        super().__init__(error)
        self.status = int(status)
        self.error = str(error)
        self.payload = {"ok": False, "error": self.error}


def new_invocation_id() -> str:
    return uuid.uuid4().hex


def artifacts_root(root: Path) -> Path:
    return Path(root).resolve() / ARTIFACTS_RELATIVE


def validate_invocation_id(invocation_id: str) -> str:
    value = str(invocation_id or "")
    if INVOCATION_ID_PATTERN.fullmatch(value) is None:
        raise ArtifactError(400, "invocation_id must be 1-128 ASCII letters, digits, ._:-")
    return value


def prepare_artifact_dir(root: Path, invocation_id: str) -> Path:
    """Create the durable directory for one invocation's harvested TEMP files."""

    ident = validate_invocation_id(invocation_id)
    dest = artifacts_root(root) / ident
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def _safe_relative(name: str) -> Path:
    raw = str(name or "").replace("\\", "/").strip()
    if not raw or raw.startswith("/") or raw.startswith("~"):
        raise ArtifactError(400, "artifact name must be a relative file path")
    parts = [part for part in raw.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        raise ArtifactError(400, "artifact name must not contain '..' or be empty")
    return Path(*parts)


def list_artifact_files(dest: Path) -> list[dict[str, Any]]:
    """Return sorted ``{name, bytes}`` rows for regular files under dest."""

    folder = Path(dest)
    if not folder.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for path in sorted(folder.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            try:
                rel = path.relative_to(folder).as_posix()
                size = path.stat().st_size
            except (OSError, ValueError):
                continue
            rows.append({"name": rel, "bytes": int(size)})
            if len(rows) >= MAX_ARTIFACT_FILES:
                break
    except OSError:
        return rows
    return rows


def list_invocation_artifacts(root: Path, invocation_id: str) -> dict[str, Any]:
    ident = validate_invocation_id(invocation_id)
    folder = artifacts_root(root) / ident
    if not folder.is_dir():
        raise ArtifactError(404, f"unknown invocation artifacts: {ident}")
    files = list_artifact_files(folder)
    return {"ok": True, "invocation_id": ident, "files": files}


def read_invocation_artifact(root: Path, invocation_id: str, name: str) -> tuple[bytes, str, str]:
    """Return ``(body, content_type, filename)`` for one harvested file."""

    ident = validate_invocation_id(invocation_id)
    relative = _safe_relative(name)
    folder = (artifacts_root(root) / ident).resolve()
    if not folder.is_dir():
        raise ArtifactError(404, f"unknown invocation artifacts: {ident}")
    target = (folder / relative).resolve()
    try:
        target.relative_to(folder)
    except ValueError as exc:
        raise ArtifactError(400, "artifact name escapes the invocation directory") from exc
    if not target.is_file() or target.is_symlink():
        raise ArtifactError(404, f"unknown artifact: {relative.as_posix()}")
    try:
        body = target.read_bytes()
    except OSError as exc:
        raise ArtifactError(404, f"unknown artifact: {relative.as_posix()}") from exc
    guessed, _encoding = mimetypes.guess_type(target.name)
    content_type = guessed or "application/octet-stream"
    return body, content_type, relative.name


def serve_invocation_artifact(
    root: Path, invocation_id: str, name: str = ""
) -> tuple[int, str, bytes, dict[str, str]]:
    """GET dispatcher: listing JSON when ``name`` is empty, otherwise file bytes.

    Return ``(status, content_type, body, extra_headers)``. Baseline trees
    lack this function, so acceptance probes can fail closed without crashing.
    """

    ident = str(invocation_id or "")
    relative = str(name or "").strip()
    if not relative:
        payload = list_invocation_artifacts(root, ident)
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        return 200, "application/json", body, {}
    data, content_type, filename = read_invocation_artifact(root, ident, relative)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return 200, content_type, data, headers
