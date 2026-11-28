"""Store invocation output and stream verified byte ranges from its regular files."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import stat
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO, Iterable, Iterator, NamedTuple, Sequence
from urllib.parse import quote

from blackhole_agent.http_preconditions import evaluate_http_preconditions

ARTIFACTS_RELATIVE = Path(".blackhole-agent") / "invocation-artifacts"
INVOCATION_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,128}\Z")
MAX_ARTIFACT_FILES = 256
_BLOCK_BYTES = 256 * 1024


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
    if value in {".", ".."} or INVOCATION_ID_PATTERN.fullmatch(value) is None:
        raise ArtifactError(400, "expected a 1-128 character invocation ID using letters, digits, dots, _ or -")
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
    if not parts or ".." in parts:
        raise ArtifactError(400, "artifact name must not contain '..' or be empty")
    return Path(*parts)


def list_artifact_files(dest: Path) -> list[dict[str, Any]]:
    """Return sorted ``{name, bytes}`` rows for regular files under dest."""

    folder = Path(dest)
    rows: list[dict[str, Any]] = []
    try:
        for path in sorted(folder.rglob("*")):
            try:
                info = path.lstat()
            except OSError:
                continue
            if not stat.S_ISREG(info.st_mode):
                continue
            rows.append({"name": path.relative_to(folder).as_posix(), "bytes": info.st_size})
            if len(rows) >= MAX_ARTIFACT_FILES:
                break
    except OSError:
        return rows
    return rows


def _artifact_folder(root: Path, invocation_id: str) -> Path:
    ident = validate_invocation_id(invocation_id)
    folder = artifacts_root(root).resolve() / ident
    if not folder.is_dir() or folder.resolve() != folder:
        raise ArtifactError(404, f"unknown invocation artifacts: {ident}")
    return folder


def list_invocation_artifacts(root: Path, invocation_id: str) -> dict[str, Any]:
    folder = _artifact_folder(root, invocation_id)
    return {"ok": True, "invocation_id": folder.name, "files": list_artifact_files(folder)}


def _artifact_path(root: Path, invocation_id: str, name: str) -> Path:
    folder = _artifact_folder(root, invocation_id)
    relative = _safe_relative(name)
    target = (folder / relative).resolve()
    if not target.is_relative_to(folder):
        raise ArtifactError(400, "artifact name escapes the invocation directory")
    if not target.is_file() or target != folder / relative:
        raise ArtifactError(404, f"unknown artifact: {relative.as_posix()}")
    return target


class ArtifactResponse(NamedTuple):
    status: int
    content_type: str
    length: int | None
    headers: dict[str, str]
    chunks: Iterable[bytes]


def _fingerprint(source: BinaryIO, size: int) -> list[bytes]:
    """One digest per block lets a later read verify every byte before sending it."""
    checksums = []
    for offset in range(0, size, _BLOCK_BYTES):
        count = min(_BLOCK_BYTES, size - offset)
        block = source.read(count)
        if len(block) != count:
            raise ArtifactError(409, "artifact changed while opening the download")
        checksums.append(hashlib.sha256(block).digest())
    return checksums


def _verified_slice(source: BinaryIO, checksums: list[bytes], size: int, start: int, stop: int) -> Iterator[bytes]:
    offset = start - start % _BLOCK_BYTES
    source.seek(offset)
    while offset < stop:
        block = source.read(min(_BLOCK_BYTES, size - offset))
        if hashlib.sha256(block).digest() != checksums[offset // _BLOCK_BYTES]:
            raise OSError("artifact changed during transfer")
        yield block[max(start - offset, 0):stop - offset]
        offset += len(block)


@contextmanager
def open_artifact_response(
    root: Path, invocation_id: str, name: str = "", fields: Sequence[tuple[str, str]] = (),
) -> Iterator[ArtifactResponse]:
    """Open a listing or a single-range GET. The caller consumes chunks inside the context."""
    if not str(name or "").strip():
        payload = list_invocation_artifacts(root, invocation_id)
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        yield ArtifactResponse(200, "application/json", len(body), {}, (body,))
        return

    path = _artifact_path(root, invocation_id, name)
    try:
        source = path.open("rb")
    except OSError as exc:
        raise ArtifactError(404, f"cannot open artifact: {name}") from exc
    with source:
        try:
            size = os.fstat(source.fileno()).st_size
            checksums = _fingerprint(source, size)
        except OSError as exc:
            raise ArtifactError(409, "artifact unavailable during download") from exc
        etag = '"' + hashlib.sha256(b"".join(checksums)).hexdigest() + '"'
        decision = evaluate_http_preconditions("GET", fields, etag=etag, length=size)
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        filename = quote(path.name, safe="")
        disposition = f'filename="{filename}"' if filename == path.name else f"filename*=UTF-8''{filename}"
        headers = {"Accept-Ranges": "bytes", "ETag": etag, "Content-Disposition": f"attachment; {disposition}"}
        status = decision["status"]
        if decision["content_range"]:
            headers["Content-Range"] = decision["content_range"]
        if status in (304, 412, 416):
            yield ArtifactResponse(status, content_type, None if status == 304 else 0, headers, ())
            return
        start, stop = 0, size
        if status == 206 and len(decision["ranges"]) == 1:
            start, last = decision["ranges"][0]
            stop = last + 1
        else:
            status = 200  # Multipart selections and partial selections of an empty file fall back to a full GET.
        yield ArtifactResponse(status, content_type, stop - start, headers,
                               _verified_slice(source, checksums, size, start, stop))


def serve_invocation_artifact(root: Path, invocation_id: str, name: str = "") -> tuple[int, str, bytes, dict[str, str]]:
    """Materialize a response for in-process callers that need its bytes."""
    with open_artifact_response(root, invocation_id, name) as response:
        return response.status, response.content_type, b"".join(response.chunks), response.headers


def read_invocation_artifact(root: Path, invocation_id: str, name: str) -> tuple[bytes, str, str]:
    relative = _safe_relative(name)
    _, content_type, body, _ = serve_invocation_artifact(root, invocation_id, relative.as_posix())
    return body, content_type, relative.name
