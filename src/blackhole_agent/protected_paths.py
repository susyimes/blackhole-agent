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
    """

    if not base or not head:
        return (), "protected-path gate is missing a base or candidate head"
    try:
        completed = command_runner(
            ["git", "diff", "--name-only", "--diff-filter=ACDMRT", base, head],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return (), f"protected-path gate could not list candidate diff: {error}"
    if int(getattr(completed, "returncode", 1)) != 0:
        detail = (getattr(completed, "stderr", "") or getattr(completed, "stdout", "") or "").strip()
        return (), detail or "protected-path gate could not list candidate diff"
    paths = unique_paths((completed.stdout or "").splitlines())
    return paths, ""


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
