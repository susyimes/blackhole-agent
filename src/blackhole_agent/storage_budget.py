"""Shared logical-byte budget for Blackhole-owned local storage.

One budget covers the main repository, managed mission directories, and
temporary outputs or provider sessions positively attributable to Blackhole.
The 30 GiB cap and 24 GiB preventive mark are operator policy, not an
operating-system quota: a fresh measurement is required before the cap can
be reported as satisfied.

Sizes are logical file lengths (``st_size``). Directory junctions and
symlinks are not followed. Their targets are listed and are never reported
as zero bytes. Hard links can be counted once per directory entry.
"""

from __future__ import annotations

import json
import os
import stat
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

POLICY_ID = "BA_LOCAL_STORAGE_BUDGET_V1"
SCHEMA_VERSION = 1
SIZE_KIND = "logical_file_size"
CAP_BYTES = 32_212_254_720
PREVENTIVE_BYTES = 25_769_803_776
DEFAULT_LOG_TAIL_BYTES = 65_536
_REPARSE = 0x400
_REPRO_DIRS = frozenset(
    {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", "htmlcov"}
)
_REPRO_SUFFIXES = frozenset({".pyc", ".pyo"})
_PROTECTED_PARTS = frozenset({".git", ".venv"})
_PROTECTED_NAMES = frozenset(
    {".env", "credentials.json", "credentials", "secrets.json", "id_rsa", "id_ed25519"}
)
_SAMPLE_LIMIT = 20


@dataclass(frozen=True)
class BudgetPolicy:
    """Byte thresholds. Tests pass a small policy; production uses 24/30 GiB."""

    cap_bytes: int = CAP_BYTES
    preventive_bytes: int = PREVENTIVE_BYTES
    log_tail_bytes: int = DEFAULT_LOG_TAIL_BYTES

    def __post_init__(self) -> None:
        if self.cap_bytes < 1 or self.preventive_bytes < 1 or self.log_tail_bytes < 1:
            raise ValueError("budget thresholds must be positive")
        if self.preventive_bytes > self.cap_bytes:
            raise ValueError("preventive threshold cannot exceed the cap")


def default_ba_roots(repo_path: Path) -> list[Path]:
    """Main repository plus sibling managed worktree directories.

    Unbound missions use ``.{repo}-unbound-worktrees``. Older evolution
    checkouts use ``.{repo}-blackhole-worktrees``. Both are BA-owned.
    """

    repo = Path(repo_path)
    roots = [repo]
    parent = repo.parent
    prefix = f".{repo.name}-"
    if not parent.is_dir():
        return roots
    try:
        children = list(parent.iterdir())
    except OSError:
        return roots
    for child in children:
        name = child.name
        if name.startswith(prefix) and name.endswith("-worktrees"):
            roots.append(child)
    return roots


def discover_attributable_roots() -> list[Path]:
    """Temp outputs and Grok session directories positively attributable to BA.

    The shared Grok home (vendor, downloads, plugin caches) is not included.
    Native session records are measured only; this function does not delete them.
    """

    found: list[Path] = []
    temp = os.environ.get("TEMP") or os.environ.get("TMP") or ""
    if temp and os.path.isdir(temp) and not _is_reparse(temp):
        try:
            with os.scandir(temp) as iterator:
                for entry in iterator:
                    name = entry.name.lower()
                    if name.startswith("blackhole-") or name.startswith("bh-unbound"):
                        found.append(Path(entry.path))
        except OSError:
            pass
    sessions = Path.home() / ".grok" / "sessions"
    if sessions.is_dir() and not _is_reparse(str(sessions)):
        try:
            with os.scandir(sessions) as iterator:
                for entry in iterator:
                    decoded = urllib.parse.unquote(entry.name).replace("/", "\\").lower()
                    if "blackhole-agent" in decoded:
                        found.append(Path(entry.path))
        except OSError:
            pass
    return found


def measure_roots(roots: Sequence[Path | str]) -> dict[str, Any]:
    """Sum logical sizes of regular files. Reparse points are not followed."""

    declared = [Path(root) for root in roots]
    ordered: list[Path] = []
    nested: list[dict[str, str]] = []
    for root in declared:
        container = next((earlier for earlier in ordered if _strictly_inside(earlier, root)), None)
        if container is not None:
            nested.append({"root": str(root), "nested_in": str(container), "outcome": "skipped_nested"})
            continue
        ordered.append(root)
    per_root: list[dict[str, Any]] = []
    for root in ordered:
        per_root.append(_measure_one(root))
    logical = sum(int(item["logical_bytes"]) for item in per_root)
    files = sum(int(item["file_count"]) for item in per_root)
    unmeasured = [row for item in per_root for row in item["unmeasured_owned"]]
    reparses = [row for item in per_root for row in item["reparse_not_followed"]]
    return {
        "size_kind": SIZE_KIND,
        "logical_bytes": logical,
        "file_count": files,
        "complete": not unmeasured,
        "roots": per_root,
        "nested_roots": nested,
        "unmeasured_owned_count": len(unmeasured),
        "unmeasured_owned": unmeasured[:_SAMPLE_LIMIT],
        "reparse_not_followed_count": len(reparses),
        "reparse_not_followed": reparses[:_SAMPLE_LIMIT],
        "honesty": (
            "logical file sizes of regular files; reparse targets were not followed "
            "and are not reported as zero bytes; not an operating-system disk quota"
        ),
    }


def govern_expansion(
    roots: Sequence[Path | str],
    *,
    additional_bytes: int = 0,
    policy: BudgetPolicy | None = None,
    closed_logs: Sequence[Path | str] = (),
    scratch_dirs: Sequence[Path | str] = (),
    active_paths: Sequence[Path | str] = (),
    receipt_path: Path | str | None = None,
) -> dict[str, Any]:
    """Measure, reclaim only named expendable targets when required, then authorize.

    Housekeeping runs when the measured lower bound is already at the preventive
    threshold, or when the next addition would meet or cross the cap. Explicit
    paths are validated again immediately before each rotation or delete. A
    broad root, ``.git``, credentials, active paths, and reparse points are
    not removed. An incomplete measurement refuses expansion and does not
    report the cap as satisfied.
    """

    chosen = policy or BudgetPolicy()
    if additional_bytes < 0:
        raise ValueError("additional_bytes cannot be negative")
    before = measure_roots(roots)
    needs_housekeeping = _needs_housekeeping(before, additional_bytes, chosen)
    actions: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    if needs_housekeeping:
        actions, skipped = _maintain(
            before,
            closed_logs=closed_logs,
            scratch_dirs=scratch_dirs,
            active_paths=active_paths,
            tail_bytes=chosen.log_tail_bytes,
        )
        after = measure_roots(roots)
    else:
        after = before
    allowed, reason, cap_satisfied = _authorize(after, additional_bytes, chosen)
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "policy": POLICY_ID,
        "size_kind": SIZE_KIND,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "cap_bytes": chosen.cap_bytes,
        "preventive_bytes": chosen.preventive_bytes,
        "log_tail_bytes": chosen.log_tail_bytes,
        "roots": [str(Path(root)) for root in roots],
        "bytes_before": int(before["logical_bytes"]),
        "bytes_after": int(after["logical_bytes"]),
        "file_count_before": int(before["file_count"]),
        "file_count_after": int(after["file_count"]),
        "measurement_before": _compact_measurement(before),
        "measurement_after": _compact_measurement(after),
        "cleanup_targets": actions,
        "skipped": skipped,
        "expansion": {
            "allowed": allowed,
            "reason": reason,
            "additional_bytes": additional_bytes,
            "cap_satisfied": cap_satisfied,
        },
        "honesty": after["honesty"],
    }
    if receipt_path is not None:
        _write_receipt(Path(receipt_path), receipt)
    return receipt


class StorageBudgetRefusal(RuntimeError):
    """Mission creation stopped before a worktree checkout.

    ``reason`` is the governor expansion reason (``at_cap``,
    ``would_cross_cap``, or ``measurement_incomplete``). The receipt is the
    measurement that produced the refusal. No worktree directory is created
    by this exception.
    """

    def __init__(self, reason: str, receipt: dict[str, Any]) -> None:
        self.reason = str(reason or "refused")
        self.receipt = receipt
        logical = receipt.get("bytes_after")
        cap = receipt.get("cap_bytes")
        super().__init__(
            f"storage budget refused mission worktree: {self.reason} "
            f"(logical_bytes={logical} cap_bytes={cap})"
        )


def mission_checkout_roots(repo_path: Path) -> list[Path]:
    """Repository plus its managed worktree directories.

    Host temp outputs and provider session homes are not part of this
    decision. They are not reported as zero bytes; a caller that needs them
    measures them separately.
    """

    return default_ba_roots(Path(repo_path))


def authorize_mission_worktree(repo_path: Path) -> dict[str, Any]:
    """Measure checkout roots and refuse when a new worktree is not allowed.

    ``CAP_BYTES`` and ``PREVENTIVE_BYTES`` are read at call time so a caller
    can point a fixture at a small cap. No closed logs or scratch directories
    are passed in, so this decision does not rotate or delete files. The
    receipt is written under the repository's unbound directory.
    """

    repo = Path(repo_path)
    cap = int(CAP_BYTES)
    preventive = min(int(PREVENTIVE_BYTES), cap)
    policy = BudgetPolicy(cap_bytes=cap, preventive_bytes=preventive)
    receipt = govern_expansion(
        mission_checkout_roots(repo),
        additional_bytes=0,
        policy=policy,
        receipt_path=repo / ".blackhole-agent" / "unbound" / "storage-budget.json",
    )
    expansion = receipt.get("expansion") if isinstance(receipt.get("expansion"), dict) else {}
    if expansion.get("allowed") is not True:
        raise StorageBudgetRefusal(str(expansion.get("reason") or "refused"), receipt)
    return receipt


def _needs_housekeeping(measurement: dict[str, Any], additional_bytes: int, policy: BudgetPolicy) -> bool:
    logical = int(measurement["logical_bytes"])
    return logical >= policy.preventive_bytes or logical + additional_bytes > policy.cap_bytes or logical >= policy.cap_bytes


def _authorize(measurement: dict[str, Any], additional_bytes: int, policy: BudgetPolicy) -> tuple[bool, str, bool]:
    logical = int(measurement["logical_bytes"])
    complete = bool(measurement["complete"])
    cap_satisfied = complete and logical <= policy.cap_bytes
    if not complete:
        return False, "measurement_incomplete", False
    if logical >= policy.cap_bytes:
        return False, "at_cap", cap_satisfied
    if logical + additional_bytes > policy.cap_bytes:
        return False, "would_cross_cap", cap_satisfied
    return True, "within_cap", cap_satisfied


def _compact_measurement(measurement: dict[str, Any]) -> dict[str, Any]:
    ranked = sorted(measurement["roots"], key=lambda item: int(item["logical_bytes"]), reverse=True)
    detailed = {item["root"] for item in ranked[:12]}
    return {
        "size_kind": measurement["size_kind"],
        "logical_bytes": measurement["logical_bytes"],
        "file_count": measurement["file_count"],
        "complete": measurement["complete"],
        "unmeasured_owned_count": measurement["unmeasured_owned_count"],
        "unmeasured_owned": measurement["unmeasured_owned"],
        "reparse_not_followed_count": measurement["reparse_not_followed_count"],
        "reparse_not_followed": measurement["reparse_not_followed"],
        "nested_roots": measurement["nested_roots"],
        "roots": [
            {
                "root": item["root"],
                "logical_bytes": item["logical_bytes"],
                "file_count": item["file_count"],
                "reparse_count": item["reparse_count"],
                "unmeasured_count": item["unmeasured_count"],
                "top_children": item["top_children"] if item["root"] in detailed else [],
            }
            for item in measurement["roots"]
        ],
    }


def _measure_one(root: Path) -> dict[str, Any]:
    root_abs = os.path.abspath(root)
    unmeasured: list[dict[str, Any]] = []
    reparses: list[dict[str, Any]] = []
    children: dict[str, list[int]] = {}
    logical = 0
    files = 0
    directories = 0
    if not os.path.exists(root_abs) and not os.path.lexists(root_abs):
        unmeasured.append({"path": root_abs, "reason": "root missing"})
        return _root_payload(root_abs, 0, 0, 0, 0, unmeasured, reparses, children)
    if _is_reparse(root_abs):
        reparses.append(_reparse_record(root_abs, root_abs))
        unmeasured.append({"path": root_abs, "reason": "root is a reparse point and was not followed"})
        return _root_payload(root_abs, 0, 0, 0, 1, unmeasured, reparses, children)
    if os.path.isfile(root_abs):
        try:
            st = os.lstat(root_abs)
        except OSError as exc:
            unmeasured.append({"path": root_abs, "reason": str(exc)})
            return _root_payload(root_abs, 0, 0, 0, 0, unmeasured, reparses, children)
        if stat.S_ISREG(st.st_mode):
            return _root_payload(root_abs, int(st.st_size), 1, 0, 0, unmeasured, reparses, children)
        unmeasured.append({"path": root_abs, "reason": "not a regular file"})
        return _root_payload(root_abs, 0, 0, 0, 0, unmeasured, reparses, children)
    stack = [root_abs]
    while stack:
        current = stack.pop()
        try:
            iterator = os.scandir(current)
        except OSError as exc:
            unmeasured.append({"path": current, "reason": str(exc)})
            continue
        with iterator:
            for entry in iterator:
                try:
                    st = entry.stat(follow_symlinks=False)
                except OSError as exc:
                    unmeasured.append({"path": entry.path, "reason": str(exc)})
                    continue
                if (getattr(st, "st_file_attributes", 0) & _REPARSE) or entry.is_symlink():
                    record = _reparse_record(entry.path, root_abs)
                    reparses.append(record)
                    if record.get("counts_as_unmeasured_owned"):
                        unmeasured.append(
                            {
                                "path": entry.path,
                                "reason": str(record.get("unmeasured_reason") or "reparse target not measured"),
                            }
                        )
                    continue
                if stat.S_ISDIR(st.st_mode):
                    directories += 1
                    stack.append(entry.path)
                    continue
                if not stat.S_ISREG(st.st_mode):
                    unmeasured.append({"path": entry.path, "reason": "not a regular file"})
                    continue
                logical += int(st.st_size)
                files += 1
                relative = os.path.relpath(entry.path, root_abs)
                child = relative.split(os.sep, 1)[0]
                bucket = children.setdefault(child, [0, 0])
                bucket[0] += int(st.st_size)
                bucket[1] += 1
    return _root_payload(root_abs, logical, files, directories, len(reparses), unmeasured, reparses, children)


def _root_payload(
    root_abs: str,
    logical: int,
    files: int,
    directories: int,
    reparse_count: int,
    unmeasured: list[dict[str, Any]],
    reparses: list[dict[str, Any]],
    children: dict[str, list[int]],
) -> dict[str, Any]:
    top = sorted(children.items(), key=lambda item: item[1][0], reverse=True)[:15]
    return {
        "root": root_abs,
        "logical_bytes": logical,
        "file_count": files,
        "directory_count": directories,
        "reparse_count": reparse_count,
        "unmeasured_count": len(unmeasured),
        "unmeasured_owned": unmeasured,
        "reparse_not_followed": reparses,
        "top_children": [
            {"name": name, "logical_bytes": bucket[0], "files": bucket[1]} for name, bucket in top
        ],
    }


def _reparse_record(path: str, root_abs: str) -> dict[str, Any]:
    target_raw = None
    try:
        target_raw = os.readlink(path)
    except OSError:
        target_raw = None
    target = _link_target(path, target_raw) if target_raw else None
    record: dict[str, Any] = {
        "path": os.path.abspath(path),
        "target": target,
        "followed": False,
        "target_bytes_counted": False,
    }
    if target is None:
        record["counts_as_unmeasured_owned"] = True
        record["unmeasured_reason"] = "reparse target could not be read"
        return record
    if not _inside(root_abs, target):
        record["target_outside_root"] = True
        record["counts_as_unmeasured_owned"] = False
        record["note"] = "outside target was not followed and is not counted as zero bytes"
        return record
    reachable = not _is_reparse(target) and not _reparse_between(root_abs, target)
    record["target_inside_root"] = True
    record["target_reachable_without_link"] = reachable
    if reachable:
        record["counts_as_unmeasured_owned"] = False
        record["note"] = "target path is inside the root and is counted on its own directory entry"
    else:
        record["counts_as_unmeasured_owned"] = True
        record["unmeasured_reason"] = "internal reparse target was not followed"
    return record


def _maintain(
    measurement: dict[str, Any],
    *,
    closed_logs: Sequence[Path | str],
    scratch_dirs: Sequence[Path | str],
    active_paths: Sequence[Path | str],
    tail_bytes: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    roots = [str(item["root"]) for item in measurement["roots"]]
    active = [os.path.abspath(path) for path in active_paths]
    actions: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for raw in closed_logs:
        outcome = _rotate_log(Path(raw), roots, active, tail_bytes)
        (actions if outcome["outcome"] == "rotated" else skipped).append(outcome)
    for raw in scratch_dirs:
        deleted, left = _reclaim_scratch(Path(raw), roots, active)
        actions.extend(deleted)
        skipped.extend(left)
    return actions, skipped


def _rotate_log(path: Path, roots: Sequence[str], active: Sequence[str], tail_bytes: int) -> dict[str, Any]:
    absolute = os.path.abspath(path)
    refusal = _refuse_mutation(absolute, roots, active, kind="log")
    if refusal:
        return {"path": absolute, "action": "rotate_log_tail", "outcome": "skipped", "reason": refusal}
    if not _is_log_name(absolute):
        return {
            "path": absolute,
            "action": "rotate_log_tail",
            "outcome": "skipped",
            "reason": "not a stdout or stderr log",
        }
    try:
        size = os.path.getsize(absolute)
    except OSError as exc:
        return {"path": absolute, "action": "rotate_log_tail", "outcome": "skipped", "reason": str(exc)}
    if size <= tail_bytes:
        return {
            "path": absolute,
            "action": "rotate_log_tail",
            "outcome": "skipped",
            "reason": "already within diagnostic tail",
        }
    try:
        with open(absolute, "rb") as handle:
            handle.seek(max(0, size - tail_bytes))
            data = handle.read()
    except OSError as exc:
        return {"path": absolute, "action": "rotate_log_tail", "outcome": "skipped", "reason": str(exc)}
    newline = data.find(b"\n")
    if 0 < newline < min(256, len(data) - 1):
        data = data[newline + 1 :]
    temporary = absolute + ".tail-tmp"
    if _refuse_mutation(temporary, roots, active, kind="log"):
        return {
            "path": absolute,
            "action": "rotate_log_tail",
            "outcome": "skipped",
            "reason": "tail temporary path is outside the measured root",
        }
    try:
        with open(temporary, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, absolute)
    except OSError as exc:
        try:
            if os.path.lexists(temporary):
                os.remove(temporary)
        except OSError:
            pass
        return {"path": absolute, "action": "rotate_log_tail", "outcome": "skipped", "reason": str(exc)}
    try:
        after = os.path.getsize(absolute)
    except OSError:
        after = len(data)
    return {
        "path": absolute,
        "action": "rotate_log_tail",
        "outcome": "rotated",
        "bytes_before": size,
        "bytes_after": after,
        "reason": "closed stdout/stderr log replaced with its diagnostic tail",
    }


def _reclaim_scratch(
    scratch: Path, roots: Sequence[str], active: Sequence[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    absolute = os.path.abspath(scratch)
    deleted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    container = _owning_root(absolute, roots)
    if container is None or not _strictly_inside(container, absolute):
        skipped.append(
            {
                "path": absolute,
                "action": "delete_scratch",
                "outcome": "skipped",
                "reason": "scratch directory must stay strictly inside a measured root",
            }
        )
        return deleted, skipped
    if _is_reparse(absolute) or _reparse_between(container, absolute) or _protected(absolute):
        skipped.append(
            {
                "path": absolute,
                "action": "delete_scratch",
                "outcome": "skipped",
                "reason": "scratch directory is protected or a reparse point",
            }
        )
        return deleted, skipped
    candidates: list[str] = []
    repro_dirs: list[str] = []
    stack = [absolute]
    while stack:
        current = stack.pop()
        if _is_reparse(current):
            skipped.append(
                {
                    "path": current,
                    "action": "delete_scratch",
                    "outcome": "skipped",
                    "reason": "reparse point was not followed or deleted",
                }
            )
            continue
        try:
            iterator = os.scandir(current)
        except OSError as exc:
            skipped.append(
                {"path": current, "action": "delete_scratch", "outcome": "skipped", "reason": str(exc)}
            )
            continue
        with iterator:
            for entry in iterator:
                if _is_reparse(entry.path):
                    skipped.append(
                        {
                            "path": os.path.abspath(entry.path),
                            "action": "delete_scratch",
                            "outcome": "skipped",
                            "reason": "reparse point was not followed or deleted",
                        }
                    )
                    continue
                try:
                    st = entry.stat(follow_symlinks=False)
                except OSError as exc:
                    skipped.append(
                        {
                            "path": entry.path,
                            "action": "delete_scratch",
                            "outcome": "skipped",
                            "reason": str(exc),
                        }
                    )
                    continue
                if stat.S_ISDIR(st.st_mode):
                    if Path(entry.path).name in _REPRO_DIRS:
                        repro_dirs.append(entry.path)
                    stack.append(entry.path)
                    continue
                if stat.S_ISREG(st.st_mode) and _reproducible(absolute, entry.path):
                    candidates.append(entry.path)
    for candidate in candidates:
        result = _unlink_reproducible(candidate, container, absolute, active)
        if result["outcome"] == "deleted":
            deleted.append(result)
        else:
            skipped.append(result)
    _remove_empty_repro_dirs(repro_dirs, container, absolute, active, skipped)
    return deleted, skipped


def _unlink_reproducible(path: str, root: str, scratch: str, active: Sequence[str]) -> dict[str, Any]:
    absolute = os.path.abspath(path)
    refusal = _refuse_mutation(absolute, [root], active, kind="scratch")
    if refusal:
        return {"path": absolute, "action": "delete_scratch", "outcome": "skipped", "reason": refusal}
    if not _strictly_inside(scratch, absolute) or not _reproducible(scratch, absolute):
        return {
            "path": absolute,
            "action": "delete_scratch",
            "outcome": "skipped",
            "reason": "path is not reproducible scratch inside the declared directory",
        }
    if _is_reparse(absolute) or not os.path.isfile(absolute):
        return {
            "path": absolute,
            "action": "delete_scratch",
            "outcome": "skipped",
            "reason": "path changed before deletion",
        }
    try:
        size = os.path.getsize(absolute)
        os.remove(absolute)
    except OSError as exc:
        return {"path": absolute, "action": "delete_scratch", "outcome": "skipped", "reason": str(exc)}
    return {
        "path": absolute,
        "action": "delete_scratch",
        "outcome": "deleted",
        "bytes_before": size,
        "bytes_after": 0,
        "reason": "reproducible scratch file removed",
    }


def _remove_empty_repro_dirs(
    repro_dirs: Sequence[str],
    root: str,
    scratch: str,
    active: Sequence[str],
    skipped: list[dict[str, Any]],
) -> None:
    for current in sorted(repro_dirs, key=lambda item: len(item), reverse=True):
        absolute = os.path.abspath(current)
        if _is_reparse(absolute) or _refuse_mutation(absolute, [root], active, kind="scratch"):
            continue
        if not _strictly_inside(scratch, absolute) or Path(absolute).name not in _REPRO_DIRS:
            continue
        try:
            os.rmdir(absolute)
        except OSError as exc:
            skipped.append(
                {
                    "path": absolute,
                    "action": "delete_scratch",
                    "outcome": "skipped",
                    "reason": str(exc),
                }
            )


def _refuse_mutation(path: str, roots: Iterable[str], active: Sequence[str], *, kind: str) -> str:
    absolute = os.path.abspath(path)
    if _is_reparse(absolute):
        return "reparse point is not modified"
    root = _owning_root(absolute, roots)
    if root is None:
        return "path is outside every measured root"
    if _reparse_between(root, absolute):
        return "path traverses a reparse point"
    if kind == "scratch" and not _strictly_inside(root, absolute):
        return "refusing to modify a measured root itself"
    if _protected(absolute):
        return "protected git, environment, or credential path"
    if _is_active(absolute, active):
        return "path is in the active set"
    return ""


def _write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    absolute = os.path.abspath(path)
    parent = os.path.dirname(absolute)
    os.makedirs(parent, exist_ok=True)
    temporary = absolute + ".tmp"
    payload = json.dumps(receipt, indent=2, sort_keys=True).encode("utf-8")
    with open(temporary, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, absolute)


def _is_log_name(path: str) -> bool:
    name = Path(path).name.lower()
    return name.endswith(".stdout.log") or name.endswith(".stderr.log") or name.endswith(
        ".stdout"
    ) or name.endswith(".stderr")


def _reproducible(scratch: str, path: str) -> bool:
    relative = os.path.relpath(os.path.abspath(path), os.path.abspath(scratch))
    parts = Path(relative).parts
    if any(part in _REPRO_DIRS for part in parts[:-1]):
        return True
    return Path(path).suffix.lower() in _REPRO_SUFFIXES


def _protected(path: str) -> bool:
    parts = {part.casefold() for part in Path(path).parts}
    if parts & _PROTECTED_PARTS:
        return True
    name = Path(path).name.casefold()
    if name in _PROTECTED_NAMES:
        return True
    return name.endswith(".pem") or name.endswith(".key")


def _is_active(path: str, active: Sequence[str]) -> bool:
    absolute = _norm(path)
    for item in active:
        item_abs = _norm(item)
        if absolute == item_abs or _inside(item, path):
            return True
    return False


def _owning_root(path: str, roots: Iterable[str]) -> str | None:
    matches = [root for root in roots if _inside(root, path)]
    if not matches:
        return None
    return max(matches, key=lambda item: len(_norm(item)))


def _inside(parent: Path | str, child: Path | str) -> bool:
    parent_norm = _norm(parent)
    child_norm = _norm(child)
    try:
        common = _norm(os.path.commonpath([parent_norm, child_norm]))
    except ValueError:
        return False
    return common == parent_norm


def _strictly_inside(parent: Path | str, child: Path | str) -> bool:
    return _inside(parent, child) and _norm(parent) != _norm(child)


def _norm(path: Path | str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _is_reparse(path: str) -> bool:
    try:
        st = os.lstat(path)
    except OSError:
        return False
    if getattr(st, "st_file_attributes", 0) & _REPARSE:
        return True
    return stat.S_ISLNK(st.st_mode)


def _reparse_between(root: str, path: str) -> bool:
    root_norm = _norm(root)
    current = os.path.abspath(path)
    while True:
        if _norm(current) == root_norm:
            return False
        if _is_reparse(current):
            return True
        parent = os.path.dirname(current)
        if _norm(parent) == _norm(current):
            return True
        current = parent


def _link_target(path: str, raw: str) -> str:
    value = raw
    for prefix in ("\\\\?\\", "\\??\\"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break
    if os.path.isabs(value):
        return os.path.abspath(value)
    return os.path.abspath(os.path.join(os.path.dirname(path), value))
