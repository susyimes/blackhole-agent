"""Counted bh- and ba- scratch must be reclaimed once it is abandoned.

Measurement already includes a direct TEMP child named bh-mcp-plugin or
ba-grok. Reclaim used to ignore those names, so one stale tree could hold
the storage cap and mission creation would keep refusing. An aged child
with either prefix is removed. A newer bh-fp child, an aged ba-grok child
listed as active, an unrelated child, and an aged bh-acq junction plus its
target stay.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path


def _quiet_rmtree(path: Path) -> None:
    def _onerror(func, name, _exc) -> None:
        try:
            os.chmod(name, stat.S_IWRITE)
            func(name)
        except OSError:
            return

    try:
        shutil.rmtree(path, onexc=_onerror)
    except TypeError:
        shutil.rmtree(path, onerror=_onerror)
    except OSError:
        return


def _age(path: Path, seconds: float) -> None:
    stamp = time.time() - seconds
    os.utime(path, (stamp, stamp))


def observe() -> tuple[bool, dict]:
    root = Path(tempfile.mkdtemp(prefix="counted-scratch-probe-"))
    link_created = False
    try:
        temp_root = root / "temp"
        target = root / "junction-target"
        temp_root.mkdir()
        plugin = temp_root / "bh-mcp-plugin-old"
        grok = temp_root / "ba-grok-old"
        fresh = temp_root / "bh-fp-fresh"
        active = temp_root / "ba-grok-active"
        other = temp_root / "notes-oversize"
        for directory in (plugin, grok, fresh, active, target, other):
            directory.mkdir()
        (plugin / "plugin.bin").write_bytes(b"plugin")
        (grok / "probe.bin").write_bytes(b"probe")
        (fresh / "keep.bin").write_bytes(b"keep")
        (active / "live.bin").write_bytes(b"live")
        (other / "stay.bin").write_bytes(b"stay")
        (target / "payload.bin").write_bytes(b"payload")
        for path in (
            plugin / "plugin.bin",
            plugin,
            grok / "probe.bin",
            grok,
            active / "live.bin",
            active,
            other / "stay.bin",
            other,
            target / "payload.bin",
            target,
        ):
            _age(path, 48 * 60 * 60)
        link = temp_root / "bh-acq-link-old"
        created = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        link_created = created.returncode == 0 and link.exists()
        if link_created:
            _age(link, 48 * 60 * 60)

        import blackhole_agent.storage_budget as storage_budget

        reclaim = getattr(storage_budget, "reclaim_abandoned_attributable_temps", None)
        reclaim_error = ""
        report: dict = {}
        if reclaim is not None:
            try:
                report = reclaim(
                    temp_root,
                    now=time.time(),
                    minimum_age_seconds=24 * 60 * 60,
                    active_paths=[active],
                )
            except Exception as exc:  # noqa: BLE001 - the probe records the removal outcome
                reclaim_error = str(exc)
        link_reason = ""
        for item in report.get("skipped") or []:
            if isinstance(item, dict) and os.path.basename(str(item.get("path") or "")) == link.name:
                link_reason = str(item.get("reason") or "")
        removed_names = sorted(
            os.path.basename(str(item.get("path") or ""))
            for item in report.get("removed") or []
            if isinstance(item, dict)
        )
        observed = {
            "reclaim_present": reclaim is not None,
            "reclaim_error": reclaim_error,
            "removed_names": removed_names,
            "plugin_present": (plugin / "plugin.bin").exists(),
            "grok_present": (grok / "probe.bin").exists(),
            "fresh_present": (fresh / "keep.bin").exists(),
            "active_present": (active / "live.bin").exists(),
            "other_present": (other / "stay.bin").exists(),
            "link_created": link_created,
            "link_present": link.exists() if link_created else False,
            "link_reason": link_reason,
            "junction_target_present": (target / "payload.bin").exists(),
        }
        passed = (
            reclaim_error == ""
            and observed["plugin_present"] is False
            and observed["grok_present"] is False
            and observed["fresh_present"] is True
            and observed["active_present"] is True
            and observed["other_present"] is True
            and observed["junction_target_present"] is True
            and removed_names == ["ba-grok-old", "bh-mcp-plugin-old"]
            and (
                not link_created
                or (observed["link_present"] is True and "reparse" in link_reason)
            )
        )
        return passed, observed
    finally:
        link = root / "temp" / "bh-acq-link-old"
        if link.exists():
            try:
                os.rmdir(link)
            except OSError:
                pass
        _quiet_rmtree(root)


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as error:  # noqa: BLE001 - unmet outcome must still print JSON
        passed = False
        observed = {"error": str(error)}
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
