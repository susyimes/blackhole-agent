"""Outcome probe: a shared logical-byte budget gates expansion and reclaims only named expendable files.

The governor must authorize a small output below the preventive threshold
without changing files, rotate one closed stdout log and delete one
reproducible scratch file at the preventive threshold, refuse a download
that meets the cap, skip junctions that leave the measured root, and refuse
expansion when a declared root cannot be measured.

On the previous milestone this module is absent, so the probe reports
passed=false. Both outcomes exit 0.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


def _reparse(path: Path) -> bool:
    try:
        st = os.lstat(path)
    except OSError:
        return False
    return bool(getattr(st, "st_file_attributes", 0) & 0x400) or path.is_symlink()


def _remove_tree(path: Path) -> None:
    if not path.exists() and not path.is_symlink() and not os.path.lexists(path):
        return
    if _reparse(path):
        try:
            os.rmdir(path)
        except OSError:
            path.unlink(missing_ok=True)
        return
    if path.is_file():
        path.unlink()
        return
    for child in list(path.iterdir()):
        _remove_tree(child)
    path.rmdir()


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _under(budget) -> dict:
    policy = budget.BudgetPolicy(cap_bytes=10_000, preventive_bytes=5_000, log_tail_bytes=32)
    root = Path(tempfile.mkdtemp(prefix="ba-budget-under-"))
    try:
        closed = root / "closed.stdout.log"
        pyc = root / "scratch" / "pkg" / "__pycache__" / "mod.pyc"
        keep = root / "keep.txt"
        _write(closed, b"A" * 280 + b"TAILMARKER")
        _write(pyc, b"pyc-bytes")
        _write(keep, b"keep")
        before = {path: path.read_bytes() for path in (closed, pyc, keep)}
        receipt = budget.govern_expansion(
            [root],
            additional_bytes=10,
            policy=policy,
            closed_logs=[closed],
            scratch_dirs=[root / "scratch"],
            active_paths=[],
        )
        intact = all(path.read_bytes() == payload for path, payload in before.items())
        return {
            "allowed": receipt["expansion"]["allowed"] is True,
            "reason_within_cap": receipt["expansion"]["reason"] == "within_cap",
            "cap_satisfied": receipt["expansion"]["cap_satisfied"] is True,
            "intact": intact,
            "no_cleanup": receipt["cleanup_targets"] == [],
        }
    finally:
        _remove_tree(root)


def _preventive(budget) -> dict:
    policy = budget.BudgetPolicy(cap_bytes=20_000, preventive_bytes=500, log_tail_bytes=32)
    root = Path(tempfile.mkdtemp(prefix="ba-budget-prevent-"))
    try:
        closed = root / "closed.stdout.log"
        active = root / "active.stdout.log"
        credential = root / "credentials.json"
        source = root / "source.py"
        pyc = root / "scratch" / "pkg" / "__pycache__" / "mod.pyc"
        nested_secret = root / "scratch" / ".pytest_cache" / "credentials.json"
        keep = root / "scratch" / "keep.txt"
        _write(closed, b"A" * 900 + b"TAILMARKER")
        active_bytes = b"ACTIVE-MISSION-LOG" * 40
        _write(active, active_bytes)
        _write(credential, b'{"token":"keep"}')
        _write(source, b"print('source')\n")
        _write(pyc, b"reproducible-bytecode")
        _write(nested_secret, b'{"nested":"keep"}')
        _write(keep, b"keep-me")
        receipt = budget.govern_expansion(
            [root],
            additional_bytes=10,
            policy=policy,
            closed_logs=[closed, active],
            scratch_dirs=[root / "scratch"],
            active_paths=[active],
            receipt_path=root / "receipt.json",
        )
        stored = json.loads((root / "receipt.json").read_text(encoding="utf-8"))
        cleanup = {item["path"]: item for item in receipt["cleanup_targets"]}
        closed_abs = os.path.abspath(closed)
        pyc_abs = os.path.abspath(pyc)
        closed_now = closed.read_bytes()
        return {
            "allowed": receipt["expansion"]["allowed"] is True,
            "closed_tail": closed_now.endswith(b"TAILMARKER") and len(closed_now) <= 32,
            "active_unchanged": active.read_bytes() == active_bytes,
            "credential_unchanged": credential.read_bytes() == b'{"token":"keep"}',
            "nested_secret_unchanged": nested_secret.read_bytes() == b'{"nested":"keep"}',
            "source_unchanged": source.read_bytes() == b"print('source')\n",
            "keep_unchanged": keep.read_bytes() == b"keep-me",
            "pyc_removed": not pyc.exists(),
            "rotated_path": cleanup.get(closed_abs, {}).get("outcome") == "rotated",
            "deleted_path": cleanup.get(pyc_abs, {}).get("outcome") == "deleted",
            "active_skipped": any(
                item["path"] == os.path.abspath(active) and item["outcome"] == "skipped"
                for item in receipt["skipped"]
            ),
            "receipt_lists_targets": closed_abs in stored["cleanup_targets"].__repr__()
            or any(item.get("path") == closed_abs for item in stored["cleanup_targets"]),
        }
    finally:
        _remove_tree(root)


def _at_cap(budget) -> dict:
    policy = budget.BudgetPolicy(cap_bytes=4096, preventive_bytes=2048, log_tail_bytes=32)
    root = Path(tempfile.mkdtemp(prefix="ba-budget-cap-"))
    try:
        source = root / "source.py"
        payload = b"S" * 4096
        _write(source, payload)
        receipt = budget.govern_expansion([root], additional_bytes=1, policy=policy)
        return {
            "refused": receipt["expansion"]["allowed"] is False,
            "reason_at_cap": receipt["expansion"]["reason"] == "at_cap",
            "source_unchanged": source.read_bytes() == payload,
            "cap_satisfied": receipt["expansion"]["cap_satisfied"] is True,
            "no_cleanup": receipt["cleanup_targets"] == [],
        }
    finally:
        _remove_tree(root)


def _junction(budget) -> dict:
    policy = budget.BudgetPolicy(cap_bytes=10_000, preventive_bytes=5_000, log_tail_bytes=32)
    parent = Path(tempfile.mkdtemp(prefix="ba-budget-link-"))
    root = parent / "root"
    outside = parent / "outside"
    root.mkdir()
    outside.mkdir()
    inside = root / "inside.bin"
    outside_file = outside / "big.bin"
    link = root / "jump"
    _write(inside, b"I" * 123)
    _write(outside_file, b"O" * 50_000)
    created = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
        capture_output=True,
        check=False,
    )
    try:
        if created.returncode != 0 or not _reparse(link):
            return {
                "created": False,
                "detail": (created.stderr or created.stdout or b"junction was not created").decode(
                    "utf-8", errors="replace"
                ).strip(),
            }
        measured = budget.measure_roots([root])
        listed = measured["reparse_not_followed"]
        return {
            "created": True,
            "logical_bytes": measured["logical_bytes"] == 123,
            "outside_unchanged": outside_file.stat().st_size == 50_000,
            "listed": bool(listed),
            "not_followed": all(item.get("followed") is False for item in listed),
            "target_not_counted": all(item.get("target_bytes_counted") is False for item in listed),
            "complete": measured["complete"] is True,
        }
    finally:
        _remove_tree(parent)


def _missing(budget) -> dict:
    policy = budget.BudgetPolicy(cap_bytes=1000, preventive_bytes=800, log_tail_bytes=32)
    missing = Path(tempfile.mkdtemp(prefix="ba-budget-missing-")) / "absent-root"
    receipt = budget.govern_expansion([missing], additional_bytes=1, policy=policy)
    return {
        "refused": receipt["expansion"]["allowed"] is False,
        "reason": receipt["expansion"]["reason"] == "measurement_incomplete",
        "cap_not_satisfied": receipt["expansion"]["cap_satisfied"] is False,
        "listed": any(item.get("reason") == "root missing" for item in receipt["measurement_after"]["unmeasured_owned"]),
    }


def _passed(flags: dict) -> bool:
    return all(value is True for value in flags.values())


def main() -> None:
    try:
        from blackhole_agent import storage_budget as budget
    except Exception as exc:
        print(
            json.dumps(
                {
                    "passed": False,
                    "observed": f"storage budget governor unavailable: {type(exc).__name__}: {exc}",
                }
            )
        )
        return
    try:
        observed = {
            "cap_bytes": budget.CAP_BYTES == 32_212_254_720,
            "preventive_bytes": budget.PREVENTIVE_BYTES == 25_769_803_776,
            "under": _under(budget),
            "preventive": _preventive(budget),
            "at_cap": _at_cap(budget),
            "junction": _junction(budget),
            "missing": _missing(budget),
        }
        passed = (
            observed["cap_bytes"]
            and observed["preventive_bytes"]
            and _passed(observed["under"])
            and _passed(observed["preventive"])
            and _passed(observed["at_cap"])
            and observed["junction"].get("created") is True
            and _passed({key: value for key, value in observed["junction"].items() if key != "created"})
            and _passed(observed["missing"])
        )
    except Exception as exc:
        print(json.dumps({"passed": False, "observed": f"probe error: {type(exc).__name__}: {exc}"}))
        return
    print(json.dumps({"passed": passed, "observed": observed}))


if __name__ == "__main__":
    main()
