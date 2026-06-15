"""Blank, revisable self-model support for blackhole-agent."""

import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SELF_MODEL_VERSION = "2026-06-15.blank-revisable"
DEFAULT_SELF_MODEL_PATH = Path("docs/self-model.md")
SELF_MODEL_READ_LIMIT = 12000

BOOTSTRAP_SELF_MODEL = """# Self Model

This file is intentionally under-specified.

It is a revisable self-description for blackhole-agent, written in the agent's own terms over time.
The agent may create, rename, remove, contradict, or leave blank any structure below this note.
Changes should be grounded in evidence from the current run.
This file grants no permissions; runtime policy, tools, tests, and rollback rules remain external constraints.

There are no required headings below this line.
"""


@dataclass(frozen=True)
class SelfModelSnapshot:
    """One bounded read of the current self-model file."""

    version: str
    captured_at: str
    path: str
    exists: bool
    sha256: str
    content: str
    truncated: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_self_model_path(repo_path: Path, self_model_path: Path | None = None) -> Path:
    """Resolve the self-model path relative to the repository root."""

    path = self_model_path or DEFAULT_SELF_MODEL_PATH
    return path if path.is_absolute() else repo_path / path


def relative_self_model_path(repo_path: Path, self_model_path: Path | None = None) -> str:
    """Return a readable repository-relative path when possible."""

    resolved = resolve_self_model_path(repo_path, self_model_path)
    try:
        return resolved.relative_to(repo_path).as_posix()
    except ValueError:
        return str(resolved)


def read_self_model_snapshot(
    repo_path: Path,
    self_model_path: Path | None = None,
    *,
    limit: int = SELF_MODEL_READ_LIMIT,
) -> SelfModelSnapshot:
    """Read the self-model without creating or prescribing its contents."""

    resolved = resolve_self_model_path(repo_path, self_model_path)
    exists = resolved.exists()
    if exists:
        raw_content = resolved.read_text(encoding="utf-8")
    else:
        raw_content = BOOTSTRAP_SELF_MODEL
    truncated = len(raw_content) > limit
    content = raw_content[:limit]
    return SelfModelSnapshot(
        version=SELF_MODEL_VERSION,
        captured_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        path=relative_self_model_path(repo_path, self_model_path),
        exists=exists,
        sha256=hashlib.sha256(raw_content.encode("utf-8")).hexdigest(),
        content=content,
        truncated=truncated,
    )


def write_self_model_snapshot(output_dir: Path, snapshot: SelfModelSnapshot, *, phase: str) -> Path:
    """Persist a snapshot artifact for replaying how self-recognition changed."""

    output_dir.mkdir(parents=True, exist_ok=True)
    payload = snapshot.to_dict()
    payload["phase"] = phase
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot_path = output_dir / f"self-model-{phase}-{timestamp}.json"
    latest_path = output_dir / f"latest-self-model-{phase}.json"
    text = _json_dumps(payload)
    snapshot_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    if phase == "after":
        (output_dir / "latest-self-model.json").write_text(text, encoding="utf-8")
    return snapshot_path


def _json_dumps(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
