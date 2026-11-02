"""Soul layer support: read the repo-root ``soul.md`` for kernel prompts.

The soul is the desire layer between the persona (procedure) and the
self-model (free-form self-description). It grants no permissions and
cannot override governance gates; a missing soul file degrades to a
short note instead of failing a run.
"""

import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOUL_VERSION = "2026-11-02.soul-reader"
DEFAULT_SOUL_PATH = Path("soul.md")
SOUL_READ_LIMIT = 12000
ONE_PAGER_HEADING = "## 一页纸"


@dataclass(frozen=True)
class SoulSnapshot:
    """One bounded read of the current soul file."""

    version: str
    captured_at: str
    path: str
    exists: bool
    sha256: str
    content: str
    truncated: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_soul_path(repo_path: Path, soul_path: Path | None = None) -> Path:
    """Resolve the soul path relative to the repository root."""

    path = soul_path or DEFAULT_SOUL_PATH
    return path if path.is_absolute() else repo_path / path


def relative_soul_path(repo_path: Path, soul_path: Path | None = None) -> str:
    """Return a readable repository-relative path when possible."""

    resolved = resolve_soul_path(repo_path, soul_path)
    try:
        return resolved.relative_to(repo_path).as_posix()
    except ValueError:
        return str(resolved)


def read_soul_snapshot(
    repo_path: Path,
    soul_path: Path | None = None,
    *,
    limit: int = SOUL_READ_LIMIT,
) -> SoulSnapshot:
    """Read the soul file without prescribing its contents.

    A missing file yields an empty snapshot: kernels skip soul guidance
    for that run instead of failing or inventing a soul on the spot.
    """

    resolved = resolve_soul_path(repo_path, soul_path)
    exists = resolved.exists()
    raw_content = resolved.read_text(encoding="utf-8") if exists else ""
    truncated = len(raw_content) > limit
    return SoulSnapshot(
        version=SOUL_VERSION,
        captured_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        path=relative_soul_path(repo_path, soul_path),
        exists=exists,
        sha256=hashlib.sha256(raw_content.encode("utf-8")).hexdigest(),
        content=raw_content[:limit],
        truncated=truncated,
    )


def extract_one_pager(content: str) -> str:
    """Return the one-pager section (from its heading to the next ``## ``)."""

    lines = content.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith(ONE_PAGER_HEADING)), None)
    if start is None:
        return ""
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return "\n".join(lines[start + 1 : end]).strip()


def render_soul_layer(snapshot: SoulSnapshot, *, style: str = "full") -> str:
    """Render the soul as prompt text for local execution kernels.

    ``full`` embeds the whole (bounded) file, for one-shot kernel tasks.
    ``one-pager`` embeds only the one-pager section plus a pointer to the
    full text, for size-bounded recurring turn prompts.
    """

    if not snapshot.exists:
        return "Soul layer: (no soul.md in this checkout; skip soul guidance, do not invent one this run)"
    header = (
        f"Soul layer ({snapshot.path}, sha256 {snapshot.sha256[:12]}): desire, below governance "
        "and the persona in authority; it grants no permissions and overrides no gate."
    )
    if style == "one-pager":
        one_pager = extract_one_pager(snapshot.content) or snapshot.content.strip()
        return (
            f"{header}\n{one_pager}\n"
            f"Full text: {snapshot.path} at the repository root. Read it in full at genesis "
            "and before choosing the scope of a change."
        )
    return f"{header}\n\n{snapshot.content.strip()}"
