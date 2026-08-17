"""Repository size ratchet: shrink-only measured size plus a grandfather list.

Measured roots cannot grow past the checked-in baseline. Grandfathered
files may exist at their recorded max, but they still count toward the
total, so adding a new plane file without deleting something else hits
the wall. The baseline file itself is a protected path; a candidate
cannot raise the ceiling and then promote the raise.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

SCHEMA_VERSION = 1
SIZE_RATCHET_RELATIVE = Path("governance") / "size-ratchet.json"
DEFAULT_MEASURED_ROOTS: tuple[str, ...] = ("src/blackhole_agent", "tests")
DEFAULT_EXCLUDE_SUFFIXES: tuple[str, ...] = (".pyc",)
DEFAULT_EXCLUDE_DIR_NAMES: tuple[str, ...] = ("__pycache__", ".ruff_cache", ".pytest_cache")
GRANDFATHER_LINE_THRESHOLD = 2000
CommandRunner = Callable[..., Any]


@dataclass(frozen=True)
class FileSize:
    path: str
    lines: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SizeRatchetReport:
    ok: bool
    total_lines: int
    baseline_lines: int
    delta: int
    exception_violations: tuple[str, ...]
    measured_files: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_repo_path(path: str) -> str:
    value = str(path or "").replace("\\", "/").strip()
    if value.startswith("./"):
        value = value[2:]
    return value.lstrip("/")


def default_manifest_path(repo_path: Path) -> Path:
    return repo_path / SIZE_RATCHET_RELATIVE


def load_manifest(repo_path: Path) -> dict[str, Any]:
    path = default_manifest_path(repo_path)
    if not path.exists():
        return {
            "version": SCHEMA_VERSION,
            "unit": "lines",
            "measured_roots": list(DEFAULT_MEASURED_ROOTS),
            "baseline_lines": 0,
            "exceptions": [],
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "version": SCHEMA_VERSION,
            "unit": "lines",
            "measured_roots": list(DEFAULT_MEASURED_ROOTS),
            "baseline_lines": 0,
            "exceptions": [],
        }
    if not isinstance(payload, dict):
        return {
            "version": SCHEMA_VERSION,
            "unit": "lines",
            "measured_roots": list(DEFAULT_MEASURED_ROOTS),
            "baseline_lines": 0,
            "exceptions": [],
        }
    return payload


def count_lines(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return 0


def _is_excluded(relative: str) -> bool:
    parts = relative.split("/")
    if any(part in DEFAULT_EXCLUDE_DIR_NAMES for part in parts):
        return True
    return any(relative.endswith(suffix) for suffix in DEFAULT_EXCLUDE_SUFFIXES)


def _list_tracked_files(
    repo_path: Path,
    roots: Iterable[str],
    *,
    command_runner: CommandRunner = subprocess.run,
) -> list[str] | None:
    try:
        completed = command_runner(
            ["git", "ls-files", "-c", "-o", "--exclude-standard", "--", *roots],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if int(getattr(completed, "returncode", 1)) != 0:
        return None
    return [normalize_repo_path(line) for line in (completed.stdout or "").splitlines() if line.strip()]


def _walk_roots(repo_path: Path, roots: Iterable[str]) -> list[str]:
    found: list[str] = []
    for root in roots:
        base = repo_path / root
        if base.is_file():
            found.append(normalize_repo_path(root))
            continue
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            relative = normalize_repo_path(str(path.relative_to(repo_path)))
            if not _is_excluded(relative):
                found.append(relative)
    return found


def measure_repo(
    repo_path: Path,
    *,
    roots: Iterable[str] | None = None,
    command_runner: CommandRunner = subprocess.run,
) -> list[FileSize]:
    measured_roots = tuple(roots) if roots is not None else DEFAULT_MEASURED_ROOTS
    tracked = _list_tracked_files(repo_path, measured_roots, command_runner=command_runner)
    relatives = tracked if tracked is not None else _walk_roots(repo_path, measured_roots)
    files: list[FileSize] = []
    seen: set[str] = set()
    for relative in relatives:
        normalized = normalize_repo_path(relative)
        if not normalized or normalized in seen or _is_excluded(normalized):
            continue
        seen.add(normalized)
        path = repo_path / normalized
        if not path.is_file():
            continue
        files.append(FileSize(path=normalized, lines=count_lines(path)))
    files.sort(key=lambda item: item.path)
    return files


def evaluate_size_ratchet(
    files: list[FileSize],
    manifest: dict[str, Any],
) -> SizeRatchetReport:
    total = sum(item.lines for item in files)
    baseline = int(manifest.get("baseline_lines") or 0)
    exceptions = {
        normalize_repo_path(str(item.get("path") or "")): int(item.get("max_lines") or 0)
        for item in manifest.get("exceptions") or []
        if isinstance(item, dict) and item.get("path")
    }
    violations: list[str] = []
    for item in files:
        max_lines = exceptions.get(item.path)
        if max_lines is None:
            continue
        if item.lines > max_lines:
            violations.append(f"{item.path}: {item.lines} > {max_lines}")
    reasons: list[str] = []
    if baseline <= 0:
        reasons.append("size ratchet baseline is missing")
    elif total > baseline:
        reasons.append(f"measured lines {total} exceed baseline {baseline}")
    if violations:
        reasons.append("grandfathered file grew past max_lines")
    return SizeRatchetReport(
        ok=not reasons,
        total_lines=total,
        baseline_lines=baseline,
        delta=total - baseline,
        exception_violations=tuple(violations),
        measured_files=len(files),
        reason="; ".join(reasons),
    )


def check_size_ratchet(
    repo_path: Path | None = None,
    *,
    command_runner: CommandRunner = subprocess.run,
) -> dict[str, Any]:
    root = repo_path or Path.cwd()
    manifest = load_manifest(root)
    roots = manifest.get("measured_roots") or list(DEFAULT_MEASURED_ROOTS)
    files = measure_repo(root, roots=roots, command_runner=command_runner)
    report = evaluate_size_ratchet(files, manifest)
    payload = report.to_dict()
    payload["ok"] = report.ok
    payload["action"] = "size_ratchet"
    payload["exceptions"] = list(manifest.get("exceptions") or [])
    return payload


def write_size_ratchet_manifest(
    repo_path: Path,
    *,
    command_runner: CommandRunner = subprocess.run,
    grandfather_threshold: int = GRANDFATHER_LINE_THRESHOLD,
) -> dict[str, Any]:
    """Write a shrink-only baseline from the current measured tree."""

    files = measure_repo(repo_path, command_runner=command_runner)
    total = sum(item.lines for item in files)
    exceptions = [
        {
            "path": item.path,
            "max_lines": item.lines,
            "reason": "grandfathered at ratchet install",
        }
        for item in files
        if item.lines >= grandfather_threshold
    ]
    payload = {
        "version": SCHEMA_VERSION,
        "unit": "lines",
        "measured_roots": list(DEFAULT_MEASURED_ROOTS),
        "baseline_lines": total,
        "exceptions": exceptions,
        "principle": "Measured size may shrink or stay; it may not grow. Raise the ceiling only with operator acknowledgment.",
    }
    path = default_manifest_path(repo_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def builtin_size_ratchet() -> dict[str, Any]:
    """Invocable smoke: a grown total fails; a shrink or hold passes."""

    files = [FileSize(path="src/blackhole_agent/unbound.py", lines=100)]
    held = evaluate_size_ratchet(files, {"baseline_lines": 100, "exceptions": []})
    grown = evaluate_size_ratchet(
        [FileSize(path="src/blackhole_agent/unbound.py", lines=120)],
        {"baseline_lines": 100, "exceptions": []},
    )
    exception_fail = evaluate_size_ratchet(
        [FileSize(path="src/blackhole_agent/capability_compounder.py", lines=201)],
        {
            "baseline_lines": 300,
            "exceptions": [{"path": "src/blackhole_agent/capability_compounder.py", "max_lines": 200}],
        },
    )
    return {
        "ok": held.ok and not grown.ok and not exception_fail.ok,
        "action": "size_ratchet_smoke",
        "held": held.to_dict(),
        "grown": grown.to_dict(),
        "exception_fail": exception_fail.to_dict(),
    }


def main() -> int:
    report = check_size_ratchet()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
