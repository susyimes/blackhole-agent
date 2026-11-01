"""Protected-path promotion gate: evolution cannot rewrite its own judges.

The conformance suite already refuses a rewritten ``unbound.py`` that breaks
the mission contract. That is not enough. A kernel task can still edit
``supervisor.py``, ``persona.py``, health-command defaults, or this gate
itself and then sail through automatic promotion.

This module is the missing judge: a candidate diff that touches the
protected-path floor is refused unless an operator explicitly acknowledges
the change. The floor is the union of the in-code defaults and the
checked-in ``governance/protected-paths.json`` list, so a candidate cannot
weaken the list and then promote the weakening.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

SCHEMA_VERSION = 1
PROTECTED_PATHS_RELATIVE = Path("governance") / "protected-paths.json"

# Floor paths: the running supervisor loads these from the *target* checkout,
# never from the candidate. JSON may add paths; it cannot remove the floor
# without also editing this module, which is itself on the floor.
DEFAULT_PROTECTED_PATHS: tuple[str, ...] = (
    "src/blackhole_agent/supervisor.py",
    "src/blackhole_agent/persona.py",
    "src/blackhole_agent/runtime_conformance.py",
    "src/blackhole_agent/capability_watchdog.py",
    "src/blackhole_agent/evolution_route.py",
    "src/blackhole_agent/protected_paths.py",
    "src/blackhole_agent/pattern_register.py",
    "src/blackhole_agent/experience_fuel.py",
    "src/blackhole_agent/size_ratchet.py",
    "governance/",
    "pyproject.toml",
    "tests/test_protected_paths.py",
    "tests/test_pattern_register.py",
    "tests/test_experience_fuel.py",
    "tests/test_size_ratchet.py",
)

PROTECTED_PATH_INSTRUCTION = (
    "Protected governance paths are off the automatic write path. "
    "Do not edit supervisor.py, persona.py, runtime_conformance.py, "
    "capability_watchdog.py, evolution_route.py, protected_paths.py, "
    "pattern_register.py, experience_fuel.py, size_ratchet.py, "
    "governance/, or pyproject.toml. A candidate that touches those "
    "paths is refused automatic promotion; an operator must acknowledge it. "
    "Evolution cannot rewrite its own judges."
)


@dataclass(frozen=True)
class ProtectedPathVerdict:
    """Outcome of the protected-path promotion gate."""

    blocked: bool
    operator_acknowledged: bool
    touched: tuple[str, ...]
    protected_paths: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_repo_path(path: str) -> str:
    value = str(path or "").replace("\\", "/").strip()
    if value.startswith("./"):
        value = value[2:]
    return value.lstrip("/")


def path_is_protected(path: str, protected_paths: tuple[str, ...] | list[str] | None = None) -> bool:
    """Return True when ``path`` matches the protected-path floor."""

    normalized = normalize_repo_path(path)
    if not normalized:
        return False
    for item in protected_paths if protected_paths is not None else DEFAULT_PROTECTED_PATHS:
        prefix = normalize_repo_path(item)
        if not prefix:
            continue
        if prefix.endswith("/"):
            if normalized == prefix.rstrip("/") or normalized.startswith(prefix):
                return True
            continue
        if normalized == prefix or normalized.startswith(prefix + "/"):
            return True
    return False


def unique_paths(paths: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for path in paths:
        normalized = normalize_repo_path(path)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return tuple(ordered)


def load_protected_paths(repo_path: Path | None = None) -> tuple[str, ...]:
    """Load the target-checkout protected list, unioned with the in-code floor."""

    extra: list[str] = []
    if repo_path is not None:
        manifest = repo_path / PROTECTED_PATHS_RELATIVE
        if manifest.exists():
            try:
                payload = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            raw = payload.get("paths") if isinstance(payload, dict) else None
            if isinstance(raw, list):
                extra = [str(item) for item in raw if str(item).strip()]
    return unique_paths([*DEFAULT_PROTECTED_PATHS, *extra])


def _lossy_process_text(payload: str | bytes | None) -> str:
    if payload is None:
        return ""
    if isinstance(payload, bytes):
        return payload.decode("utf-8", errors="replace")
    return str(payload)


_READ_ERROR = "protected-path gate could not read candidate diff"
_DECODE_ERROR = "protected-path gate could not decode candidate diff as UTF-8"
_LIST_ERROR = "protected-path gate could not list candidate diff"
_STATUS_LETTERS = frozenset("ACDMRTUXB")
_TWO_PATH_LETTERS = frozenset("RC")
_GIT_ESCAPES = {
    "\\": 0x5C,
    '"': 0x22,
    "n": 0x0A,
    "t": 0x09,
    "b": 0x08,
    "f": 0x0C,
    "r": 0x0D,
    "a": 0x07,
    "v": 0x0B,
}


def _status_letter(token: str) -> str:
    if not token or token[0] not in _STATUS_LETTERS:
        return ""
    if len(token) > 4 or any(not character.isdigit() for character in token[1:]):
        return ""
    return token[0]


def _unquote_git_path(field: str) -> tuple[str, str]:
    """Decode one git path field. C-quoted octal escapes become raw UTF-8."""

    if not field.startswith('"'):
        return field, ""
    if len(field) < 2 or not field.endswith('"'):
        return "", _LIST_ERROR
    raw = bytearray()
    index = 1
    end = len(field) - 1
    while index < end:
        character = field[index]
        if character != "\\":
            raw.extend(character.encode("utf-8"))
            index += 1
            continue
        index += 1
        if index >= end:
            return "", _LIST_ERROR
        escaped = field[index]
        if escaped in _GIT_ESCAPES:
            raw.append(_GIT_ESCAPES[escaped])
            index += 1
            continue
        if escaped not in "01234567":
            return "", _LIST_ERROR
        octal = escaped
        index += 1
        for _ in range(2):
            if index < end and field[index] in "01234567":
                octal += field[index]
                index += 1
            else:
                break
        raw.append(int(octal, 8))
    try:
        return raw.decode("utf-8"), ""
    except UnicodeDecodeError:
        return "", _DECODE_ERROR


def _paths_from_record(status: str, fields: list[str]) -> tuple[list[str], str]:
    letter = _status_letter(status)
    if not letter:
        return [], _LIST_ERROR
    needed = 2 if letter in _TWO_PATH_LETTERS else 1
    if len(fields) != needed:
        return [], _LIST_ERROR
    paths: list[str] = []
    for field in fields:
        path, error = _unquote_git_path(field)
        if error:
            return [], error
        paths.append(path)
    return paths, ""


def parse_diff_listing(payload: str | bytes | None) -> tuple[tuple[str, ...], str]:
    """Return ``(paths, error)`` for a git name-status or name-only listing.

    Missing output and invalid UTF-8 fail closed. A NUL-delimited name-status
    record keeps both ends of a rename or copy. A line-oriented listing still
    accepts the historical name-only shape and C-quoted paths.
    """

    if payload is None:
        return (), _READ_ERROR
    if isinstance(payload, bytes):
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            return (), _DECODE_ERROR
    else:
        text = str(payload)
    if not text:
        return (), ""
    paths: list[str] = []
    if "\0" in text:
        parts = text.split("\0")
        if parts and parts[-1] == "":
            parts.pop()
        index = 0
        while index < len(parts):
            status = parts[index]
            index += 1
            letter = _status_letter(status)
            needed = 2 if letter in _TWO_PATH_LETTERS else 1
            if not letter or index + needed > len(parts):
                return (), _LIST_ERROR
            found = parts[index : index + needed]
            if any(not field for field in found):
                return (), _LIST_ERROR
            paths.extend(found)
            index += needed
        return tuple(paths), ""
    for line in text.splitlines():
        if not line.strip():
            continue
        fields = line.split("\t")
        if _status_letter(fields[0]):
            found, error = _paths_from_record(fields[0], fields[1:])
            if error:
                return (), error
            paths.extend(found)
            continue
        path, error = _unquote_git_path(line.strip())
        if error:
            return (), error
        paths.append(path)
    return tuple(paths), ""


def list_changed_paths(
    repo_path: Path,
    base: str,
    head: str,
    *,
    command_runner: Callable[..., Any] = subprocess.run,
) -> tuple[tuple[str, ...], str]:
    """Return ``(paths, error)`` for the candidate diff ``base..head``.

    An empty error means the listing succeeded. The gate fails closed when
    git cannot list the diff: a candidate that hides its changes is refused.
    ``--name-only`` drops a rename's old path, and ``core.quotepath`` wraps a
    non-ASCII name in C quotes. ``-z --name-status`` keeps both rename
    endpoints and the raw path bytes. The listing is captured as bytes so a
    non-UTF-8 name cannot disappear into an empty success.
    """

    if not base or not head:
        return (), "protected-path gate is missing a base or candidate head"
    try:
        completed = command_runner(
            [
                "git",
                "-c",
                "core.quotepath=false",
                "diff",
                "--name-status",
                "-z",
                "--find-renames",
                "--diff-filter=ACDMRT",
                base,
                head,
            ],
            cwd=repo_path,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return (), f"protected-path gate could not list candidate diff: {error}"
    if int(getattr(completed, "returncode", 1)) != 0:
        detail = (
            _lossy_process_text(getattr(completed, "stderr", None))
            or _lossy_process_text(getattr(completed, "stdout", None))
        ).strip()
        return (), detail or "protected-path gate could not list candidate diff"
    paths, decode_error = parse_diff_listing(getattr(completed, "stdout", None))
    if decode_error:
        return (), decode_error
    return unique_paths(paths), ""


def evaluate_protected_paths_gate(
    changed_paths: list[str] | tuple[str, ...],
    *,
    protected_paths: tuple[str, ...] | None = None,
    operator_acknowledged: bool = False,
    listing_error: str = "",
) -> ProtectedPathVerdict:
    """Refuse automatic promotion when a candidate touches a judge path."""

    floor = protected_paths if protected_paths is not None else DEFAULT_PROTECTED_PATHS
    if listing_error:
        return ProtectedPathVerdict(
            blocked=True,
            operator_acknowledged=operator_acknowledged,
            touched=(),
            protected_paths=tuple(floor),
            reason=listing_error,
        )
    touched = tuple(path for path in unique_paths(changed_paths) if path_is_protected(path, floor))
    if touched and not operator_acknowledged:
        return ProtectedPathVerdict(
            blocked=True,
            operator_acknowledged=False,
            touched=touched,
            protected_paths=tuple(floor),
            reason="protected paths require operator acknowledgment",
        )
    return ProtectedPathVerdict(
        blocked=False,
        operator_acknowledged=operator_acknowledged,
        touched=touched,
        protected_paths=tuple(floor),
        reason="",
    )


def evaluate_candidate_protected_paths(
    *,
    target_repo_path: Path,
    candidate_repo_path: Path,
    target_before: str,
    candidate_head: str,
    operator_acknowledged: bool = False,
    command_runner: Callable[..., Any] = subprocess.run,
) -> ProtectedPathVerdict:
    """Evaluate the gate against the target checkout's protected-path floor."""

    floor = load_protected_paths(target_repo_path)
    changed, listing_error = list_changed_paths(
        candidate_repo_path,
        target_before,
        candidate_head,
        command_runner=command_runner,
    )
    if listing_error:
        changed, listing_error = list_changed_paths(
            target_repo_path,
            target_before,
            candidate_head,
            command_runner=command_runner,
        )
    return evaluate_protected_paths_gate(
        changed,
        protected_paths=floor,
        operator_acknowledged=operator_acknowledged,
        listing_error=listing_error,
    )


def builtin_protected_paths_gate() -> dict[str, Any]:
    """Invocable smoke: a judge-file diff is blocked, a behavior-file diff is not."""

    blocked = evaluate_protected_paths_gate(["src/blackhole_agent/supervisor.py"])
    allowed = evaluate_protected_paths_gate(["src/blackhole_agent/unbound.py"])
    acknowledged = evaluate_protected_paths_gate(
        ["src/blackhole_agent/supervisor.py"],
        operator_acknowledged=True,
    )
    return {
        "ok": blocked.blocked and not allowed.blocked and not acknowledged.blocked,
        "action": "protected_paths_gate",
        "blocked_reason": blocked.reason,
        "blocked_touched": list(blocked.touched),
        "allowed_touched": list(allowed.touched),
        "acknowledged_touched": list(acknowledged.touched),
    }
